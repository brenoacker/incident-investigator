from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from incident_investigation_harness.adapters.knowledge_evidence import (
    KnowledgeEvidenceAdapter,
    KnowledgeEvidenceRepositoryFake,
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

    assert [document.item.path for document in result.documents] == [allowed.path]


def test_query_returns_a_relevant_excerpt(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
) -> None:
    result = repository.query(KnowledgeEvidenceQuery(context=context, query="backoff"))

    assert result.documents[0].excerpt == "Use bounded retries and backoff."


def test_query_uses_stable_scoped_citations(
    repository: KnowledgeEvidenceRepositoryFake,
    context: InvestigationContext,
) -> None:
    query = KnowledgeEvidenceQuery(context=context, query="backoff")
    first = repository.query(query).documents[0].citation
    repeated = repository.query(query).documents[0].citation

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

    assert repository.resolve(result.documents[0].citation) == result.documents[0]


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
    with pytest.raises(AttributeError):
        getattr(repository, "create")


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
