from __future__ import annotations

import sys
import uuid
from typing import cast

from mcp.server.fastmcp import FastMCP

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.fixtures import build_source_evidence_repository
from incident_investigation_harness.source_evidence import (
    SourceEvidenceQuery,
    SourceEvidenceType,
)
from incident_investigation_harness.telemetry import instrument_evidence_query

mcp = FastMCP("source-mcp", host="0.0.0.0", port=8004)
repository = build_source_evidence_repository()


@mcp.tool()
@instrument_evidence_query("source-mcp", "query")
def query_source_evidence(
    incident_id: str,
    investigation_run_id: str,
    query: str | None = None,
    evidence_types: list[str] | None = None,
    paths: list[str] | None = None,
    refs: list[str] | None = None,
) -> dict[str, object]:
    """Query allowlisted code, diffs, and Git history as Untrusted Evidence."""
    try:
        context = InvestigationContext(
            incident_id=uuid.UUID(incident_id),
            investigation_run_id=uuid.UUID(investigation_run_id),
        )
        source_query = SourceEvidenceQuery(
            context=context,
            query=query,
            evidence_types=(
                frozenset(cast(list[SourceEvidenceType], evidence_types))
                if evidence_types
                else None
            ),
            paths=frozenset(paths) if paths else None,
            refs=frozenset(refs) if refs else None,
        )
    except ValueError as error:
        raise ValueError("invalid source evidence query") from error
    return repository.query(source_query).model_dump(mode="json")


@mcp.tool()
@instrument_evidence_query("source-mcp", "resolve-citation")
def resolve_source_evidence_citation(
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
    print("source-mcp started", file=sys.stderr)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
