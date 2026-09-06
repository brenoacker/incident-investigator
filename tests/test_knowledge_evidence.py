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


def test_knowledge_contract_enforces_allowlist_stable_citations_and_read_only() -> None:
    context = InvestigationContext(incident_id=_id("incident"), investigation_run_id=_id("run"))
    allowed = KnowledgeDocument(
        id=_id("runbook"),
        path="docs/runbooks/retry-storm.md",
        title="Retry Storm runbook",
        content="Use bounded retries and backoff.",
        document_type="runbook",
    )
    outside_allowlist = KnowledgeDocument(
        id=_id("source"),
        path="src/secret.py",
        title="Private source",
        content="should not be exposed",
        document_type="runbook",
    )
    repository = KnowledgeEvidenceRepositoryFake(
        documents=(allowed, outside_allowlist),
        allowlist=frozenset({allowed.path}),
    )

    query = KnowledgeEvidenceQuery(context=context, query="backoff")
    result = repository.query(query)
    repeated = repository.query(query)

    assert [item.item.path for item in result.documents] == [allowed.path]
    assert result.documents[0].excerpt == allowed.content
    assert result.documents[0].citation == repeated.documents[0].citation
    assert result.documents[0].citation.provider == "knowledge-mcp"
    assert result.documents[0].citation.evidence_type == "knowledge-document"
    assert repository.resolve(result.documents[0].citation) == result.documents[0]
    with pytest.raises(AttributeError):
        getattr(repository, "create")

    invalid = EvidenceCitation(
        provider="knowledge-mcp",
        incident_id=context.incident_id,
        investigation_run_id=context.investigation_run_id,
        evidence_type="knowledge-document",
        evidence_id=outside_allowlist.id,
    )
    assert repository.resolve(invalid) is None

    source_allowlisted = KnowledgeEvidenceRepositoryFake(
        documents=(outside_allowlist,), allowlist=frozenset({outside_allowlist.path})
    )
    assert source_allowlisted.query(KnowledgeEvidenceQuery(context=context)).documents == ()
    with pytest.raises(ValueError, match="authorized knowledge"):
        KnowledgeEvidenceAdapter.from_allowlist(
            root=Path("."),
            allowlist=frozenset({"src/secret.py"}),
        )


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"knowledge-test:{value}")
