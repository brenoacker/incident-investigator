from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from incident_investigation_harness.adapters.source_evidence import (
    SourceEvidenceAdapter,
    SourceEvidenceRepositoryFake,
)
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.source_evidence import (
    SourceArtifact,
    SourceEvidenceQuery,
)


def test_query_returns_allowlisted_code_diff_and_history_with_citations(
    repository: SourceEvidenceRepositoryFake, context: InvestigationContext
) -> None:
    result = repository.query(SourceEvidenceQuery(context=context))

    assert [item.item.artifact_type for item in result.artifacts] == [
        "source-code",
        "source-diff",
        "git-history",
    ]
    assert all(item.citation.provider == "source-mcp" for item in result.artifacts)
    assert all(
        item.citation.investigation_run_id == context.investigation_run_id
        for item in result.artifacts
    )


def test_citations_are_stable_and_resolvable(
    repository: SourceEvidenceRepositoryFake, context: InvestigationContext
) -> None:
    query = SourceEvidenceQuery(context=context, query="retry")
    first = repository.query(query).artifacts[0]
    repeated = repository.query(query).artifacts[0]

    assert first.citation == repeated.citation
    assert repository.resolve(first.citation) == first.model_copy(
        update={"excerpt": first.item.content}
    )


def test_query_and_resolve_reject_content_outside_allowlist(
    repository: SourceEvidenceRepositoryFake,
    context: InvestigationContext,
    outside_allowlist: SourceArtifact,
) -> None:
    query = SourceEvidenceQuery(context=context, paths=frozenset({outside_allowlist.path}))
    assert repository.query(query).artifacts == ()

    citation = EvidenceCitation(
        provider="source-mcp",
        incident_id=context.incident_id,
        investigation_run_id=context.investigation_run_id,
        evidence_type="source-code",
        evidence_id=outside_allowlist.id,
    )
    assert repository.resolve(citation) is None


def test_repository_has_no_write_checkout_or_history_mutation_interface(
    repository: SourceEvidenceRepositoryFake,
) -> None:
    for operation in ("write", "checkout", "reset", "create", "delete"):
        with pytest.raises(AttributeError):
            getattr(repository, operation)


def test_source_allowlist_rejects_oracle_paths_and_option_like_refs() -> None:
    with pytest.raises(ValueError, match="unauthorized path"):
        SourceEvidenceAdapter.from_allowlist(
            root=Path("."),
            paths=frozenset({"docs/incident-oracle.md"}),
            refs=frozenset({"HEAD"}),
        )

    with pytest.raises(ValueError, match="unauthorized ref"):
        SourceEvidenceAdapter.from_allowlist(
            root=Path("."),
            paths=frozenset({"src/app.py"}),
            refs=frozenset({"--upload-pack=evil"}),
        )


@pytest.fixture
def context() -> InvestigationContext:
    return InvestigationContext(incident_id=_id("incident"), investigation_run_id=_id("run"))


@pytest.fixture
def allowed() -> tuple[SourceArtifact, ...]:
    return tuple(
        SourceArtifact(
            id=_id(kind),
            artifact_type=kind,  # type: ignore[arg-type]
            path="src/app.py",
            revision="HEAD",
            content=content,
        )
        for kind, content in (
            ("source-code", "def retry():\n    return True"),
            ("source-diff", "+ backoff"),
            ("git-history", "abc123 add retry"),
        )
    )


@pytest.fixture
def outside_allowlist() -> SourceArtifact:
    return SourceArtifact(
        id=_id("outside"),
        artifact_type="source-code",
        path="docs/incident-oracle.md",
        revision="HEAD",
        content="private oracle",
    )


@pytest.fixture
def repository(
    allowed: tuple[SourceArtifact, ...], outside_allowlist: SourceArtifact
) -> SourceEvidenceRepositoryFake:
    return SourceEvidenceRepositoryFake(
        artifacts=allowed + (outside_allowlist,),
        paths=frozenset({"src/app.py"}),
        refs=frozenset({"HEAD"}),
    )


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"source-test:{value}")
