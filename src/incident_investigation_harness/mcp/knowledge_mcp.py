from __future__ import annotations

import sys
import uuid
from typing import cast

from mcp.server.fastmcp import FastMCP

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.fixtures import build_knowledge_evidence_repository
from incident_investigation_harness.knowledge_evidence import (
    KnowledgeDocumentType,
    KnowledgeEvidenceQuery,
)

mcp = FastMCP("knowledge-mcp", host="0.0.0.0", port=8003)
repository = build_knowledge_evidence_repository()


@mcp.tool()
def query_knowledge_evidence(
    incident_id: str,
    investigation_run_id: str,
    query: str | None = None,
    document_types: list[str] | None = None,
) -> dict[str, object]:
    """Query explicitly authorized runbooks and ADRs as Untrusted Evidence."""
    try:
        context = InvestigationContext(
            incident_id=uuid.UUID(incident_id),
            investigation_run_id=uuid.UUID(investigation_run_id),
        )
        knowledge_query = KnowledgeEvidenceQuery(
            context=context,
            query=query,
            document_types=(
                frozenset(cast(list[KnowledgeDocumentType], document_types))
                if document_types
                else None
            ),
        )
    except ValueError as error:
        raise ValueError("invalid knowledge evidence query") from error
    return repository.query(knowledge_query).model_dump(mode="json")


@mcp.tool()
def resolve_knowledge_evidence_citation(
    provider: str,
    incident_id: str,
    investigation_run_id: str,
    evidence_type: str,
    evidence_id: str,
) -> dict[str, object] | None:
    """Resolve a citation previously returned by this provider."""
    citation = EvidenceCitation.model_validate(
        {
            "provider": provider,
            "incident_id": uuid.UUID(incident_id),
            "investigation_run_id": uuid.UUID(investigation_run_id),
            "evidence_type": evidence_type,
            "evidence_id": uuid.UUID(evidence_id),
        }
    )
    resolved = repository.resolve(citation)
    return resolved.model_dump(mode="json") if resolved else None


def main() -> None:
    print("knowledge-mcp started", file=sys.stderr)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
