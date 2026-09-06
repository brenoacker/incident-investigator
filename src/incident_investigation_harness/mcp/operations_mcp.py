import sys
import uuid
from typing import Literal, cast

from mcp.server.fastmcp import FastMCP

from incident_investigation_harness.adapters.operational_evidence import (
    build_operational_evidence_repository,
)
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.operational_evidence import (
    OperationalEvidenceQuery,
    OperationalEvidenceType,
)

mcp = FastMCP("operations-mcp", host="0.0.0.0", port=8002)
repository = build_operational_evidence_repository()


@mcp.tool()
def query_operational_evidence(
    incident_id: str,
    investigation_run_id: str,
    evidence_types: list[str] | None = None,
    operation: str | None = None,
) -> dict[str, object]:
    """Query read-only logs, metrics, and traces for one Investigation Run."""
    try:
        context = InvestigationContext(
            incident_id=uuid.UUID(incident_id),
            investigation_run_id=uuid.UUID(investigation_run_id),
        )
        query = OperationalEvidenceQuery(
            context=context,
            evidence_types=(
                frozenset(cast(list[OperationalEvidenceType], evidence_types))
                if evidence_types
                else None
            ),
            operation=operation,
        )
    except ValueError as error:
        raise ValueError("invalid operational evidence query") from error
    return repository.query(query).model_dump(mode="json")


@mcp.tool()
def resolve_operational_evidence_citation(
    provider: str,
    incident_id: str,
    investigation_run_id: str,
    evidence_type: str,
    evidence_id: str,
) -> dict[str, object] | None:
    """Resolve a citation previously returned by this provider."""
    citation = EvidenceCitation(
        provider=cast(Literal["incident-mcp", "operations-mcp"], provider),
        incident_id=uuid.UUID(incident_id),
        investigation_run_id=uuid.UUID(investigation_run_id),
        evidence_type=cast(
            Literal[
                "ticket",
                "comment",
                "timeline",
                "operational-log",
                "operational-metric",
                "operational-trace",
            ],
            evidence_type,
        ),
        evidence_id=uuid.UUID(evidence_id),
    )
    resolved = repository.resolve(citation)
    return resolved.model_dump(mode="json") if resolved else None


def main() -> None:
    print("operations-mcp started", file=sys.stderr)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
