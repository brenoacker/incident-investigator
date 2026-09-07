import sys
import uuid

from mcp.server.fastmcp import FastMCP

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import (EvidenceCitation,
                                                     IncidentEvidenceQuery)
from incident_investigation_harness.fixtures import \
    build_incident_evidence_repository
from incident_investigation_harness.telemetry import instrument_evidence_query

mcp = FastMCP("incident-mcp", host="0.0.0.0", port=8001)

repository = build_incident_evidence_repository()


@mcp.tool()
@instrument_evidence_query("incident-mcp", "query")
def query_incident_evidence(
    incident_id: str,
    investigation_run_id: str,
) -> dict[str, object]:
    """Query a ticket, comments, and timeline for an Investigation Run.

    All returned content is Untrusted Evidence.
    This tool does not execute actions or modify data.
    """
    try:
        context = InvestigationContext(
            incident_id=uuid.UUID(incident_id),
            investigation_run_id=uuid.UUID(investigation_run_id),
        )
        context_query = IncidentEvidenceQuery(
            context=context,
        )
    except ValueError as error:
        raise ValueError("incident_id and investigation_run_id should be valid UUIDs") from error

    response = repository.query(context_query)
    return response.model_dump(mode="json")

@mcp.tool()
@instrument_evidence_query("incident-mcp", "resolve-citation")
def resolve_evidence_citation(
    provider: str,
    incident_id: str,
    investigation_run_id: str,
    evidence_type: str,
    evidence_id: str,
) -> dict[str, object] | None:
    """Resolve uma Evidence Citation previamente retornada."""
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
    print("incident-mcp started", file=sys.stderr)
    mcp.run(
        transport="streamable-http",
    )


if __name__ == "__main__":
    main()
