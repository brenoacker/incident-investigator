from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from incident_investigation_harness.adapters.knowledge_evidence import (
    KnowledgeEvidenceAdapter,
    KnowledgeEvidenceRepositoryFake,
    OpenAIEmbeddingAdapter,
)
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.knowledge_evidence import (
    KnowledgeDocument,
    KnowledgeEvidenceQuery,
)


def test_query_returns_only_allowlisted_documents(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
    allowed: KnowledgeDocument,
) -> None:
    result = repository.query(KnowledgeEvidenceQuery(context=context))

    assert [passage.item.path for passage in result.passages] == [allowed.path]


def test_query_returns_a_relevant_excerpt(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
) -> None:
    result = repository.query(KnowledgeEvidenceQuery(context=context, query="backoff"))

    assert result.passages[0].item.text == "Use bounded retries and backoff."


def test_query_uses_stable_scoped_citations(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
) -> None:
    query = KnowledgeEvidenceQuery(context=context, query="backoff")
    first = repository.query(query).passages[0].citation
    repeated = repository.query(query).passages[0].citation

    assert first == repeated
    assert first.provider == "knowledge-mcp"
    assert first.evidence_type == "knowledge-document"
    assert first.incident_id == context.incident_id
    assert first.investigation_run_id == context.investigation_run_id


def test_resolve_returns_an_authorized_document(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
) -> None:
    result = repository.query(KnowledgeEvidenceQuery(context=context))

    resolved = repository.resolve(result.passages[0].citation)
    assert resolved is not None
    assert resolved.item == result.passages[0].item
    assert resolved.citation == result.passages[0].citation


def test_resolve_returns_none_for_a_document_outside_the_allowlist(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
    outside_allowlist: KnowledgeDocument,
) -> None:
    citation = EvidenceCitation(
        provider="knowledge-mcp",
        incident_id=context.incident_id,
        investigation_run_id=context.investigation_run_id,
        evidence_type="knowledge-document",
        evidence_id=outside_allowlist.id,
    )

    assert repository.resolve(citation) is None


def test_allowlist_rejects_non_knowledge_paths() -> None:
    with pytest.raises(ValueError, match="authorized knowledge"):
        KnowledgeEvidenceAdapter.from_allowlist(
            root=Path("."),
            allowlist=frozenset({"src/secret.py"}),
        )


def test_repository_has_no_write_interface(
    repository: KnowledgeEvidenceRepositoryFake,
) -> None:
    attribute_name = "create"
    with pytest.raises(AttributeError):
        getattr(repository, attribute_name)


def test_query_returns_passage_revision_and_rank_metadata(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
) -> None:
    result = repository.query(KnowledgeEvidenceQuery(context=context, query="backoff"))

    passage = result.passages[0]
    assert len(passage.item.revision_id) == 64
    assert passage.item.passage_id == passage.citation.evidence_id
    assert passage.relevance_score > 0
    assert passage.match_kind in {"lexical", "semantic", "hybrid"}
    assert passage.is_untrusted is True


def test_content_change_creates_a_new_revision_and_passage_id(
    allowed: KnowledgeDocument,
    context: InvestigationContext,
) -> None:
    first = KnowledgeEvidenceRepositoryFake(
        documents=(allowed,), allowlist=frozenset({allowed.path})
    ).query(KnowledgeEvidenceQuery(context=context)).passages[0].item
    changed = allowed.model_copy(update={"content": allowed.content + " Use jitter."})
    second = KnowledgeEvidenceRepositoryFake(
        documents=(changed,), allowlist=frozenset({changed.path})
    ).query(KnowledgeEvidenceQuery(context=context)).passages[0].item

    assert first.revision_id != second.revision_id
    assert first.passage_id != second.passage_id


def test_query_respects_limit_and_returns_empty_for_weak_match(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
) -> None:
    assert len(repository.query(KnowledgeEvidenceQuery(context=context, limit=1)).passages) == 1
    assert repository.query(KnowledgeEvidenceQuery(context=context, query="unrelated" )).passages == ()


def test_unavailable_embeddings_fall_back_to_lexical_and_are_visible(
    allowed: KnowledgeDocument,
    context: InvestigationContext,
) -> None:
    class UnavailableProvider:
        name = "unavailable"
        model = "unavailable"
        dimensions = 2

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("provider unavailable")

    result = KnowledgeEvidenceRepositoryFake(
        documents=(allowed,),
        allowlist=frozenset({allowed.path}),
        embedding_provider=UnavailableProvider(),
    ).query(KnowledgeEvidenceQuery(context=context, query="backoff"))

    assert result.retrieval_mode == "lexical"
    assert result.degraded is True
    assert result.passages[0].match_kind == "lexical"


def test_openai_adapter_requires_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingAdapter(api_key=None).embed(["text"])


@pytest.fixture
def context() -> InvestigationContext:
    return InvestigationContext(
        incident_id=_id("incident"), investigation_run_id=_id("run")
    )


@pytest.fixture
def allowed() -> KnowledgeDocument:
    return KnowledgeDocument(
        id=_id("runbook"),
        path="docs/runbooks/retry-storm.md",
        title="Retry Storm runbook",
        content="Use bounded retries and backoff.",
        document_type="runbook",
    )


@pytest.fixture
def outside_allowlist() -> KnowledgeDocument:
    return KnowledgeDocument(
        id=_id("source"),
        path="src/secret.py",
        title="Private source",
        content="should not be exposed",
        document_type="runbook",
    )


@pytest.fixture
def repository(
    allowed: KnowledgeDocument,
    outside_allowlist: KnowledgeDocument,
) -> KnowledgeEvidenceRepositoryFake:
    return KnowledgeEvidenceRepositoryFake(
        documents=(allowed, outside_allowlist),
        allowlist=frozenset({allowed.path}),
    )


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"knowledge-test:{value}")
