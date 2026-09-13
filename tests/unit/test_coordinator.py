from __future__ import annotations

import uuid

import pytest

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.coordinator import (
    EvidenceQuery,
    EvidenceQueryResult,
    InvestigationCoordinator,
    InvestigationPlan,
    InvestigationStage,
    ProviderFailure,
)


def test_coordinator_follows_an_evidence_gap_and_preserves_context() -> None:
    context = _context()
    calls: list[EvidenceQuery] = []

    def query(request: EvidenceQuery) -> EvidenceQueryResult:
        calls.append(request)
        return EvidenceQueryResult(
            provider=request.provider,
            citations=(_citation(context, request.provider),),
            evidence=("useful evidence",),
            evidence_gaps=("retry policy",) if len(calls) == 1 else (),
        )

    result = InvestigationCoordinator(query=query).run(
        context,
        plan=InvestigationPlan(initial_queries=(EvidenceQuery(provider="incident-mcp", question="bound incident"),)),
        follow_up=lambda gaps: (EvidenceQuery(provider="knowledge-mcp", question=gaps[0]),),
    )

    assert [stage.stage for stage in result.stages] == [
        InvestigationStage.PLANNING,
        InvestigationStage.EVIDENCE_GATHERING,
        InvestigationStage.EVIDENCE_GATHERING,
        InvestigationStage.SYNTHESIS,
        InvestigationStage.COMPLETED,
    ]
    assert [call.provider for call in calls] == ["incident-mcp", "knowledge-mcp"]
    assert all(call.context == context for call in calls)
    assert [citation.provider for citation in result.citations] == [
        "incident-mcp", "knowledge-mcp"
    ]


def test_coordinator_stops_with_calibrated_uncertainty_when_evidence_is_missing() -> None:
    result = InvestigationCoordinator(query=lambda request: EvidenceQueryResult(
        provider=request.provider, evidence_gaps=("provider logs",)
    )).run(
        _context(),
        plan=InvestigationPlan(initial_queries=(EvidenceQuery(provider="operations-mcp", question="logs"),)),
        follow_up=lambda gaps: (),
    )

    assert result.stop_reason == "calibrated-uncertainty"
    assert result.report is None
    assert result.events[-1].payload["reason"] == "calibrated-uncertainty"


def test_coordinator_records_provider_failure_and_does_not_continue() -> None:
    def fail(request: EvidenceQuery) -> EvidenceQueryResult:
        raise ProviderFailure("operations-mcp unavailable")

    result = InvestigationCoordinator(query=fail).run(
        _context(),
        plan=InvestigationPlan(initial_queries=(EvidenceQuery(provider="operations-mcp", question="metrics"),)),
        follow_up=lambda gaps: pytest.fail("follow-up must not run"),
    )

    assert result.stop_reason == "provider-failure"
    assert result.failure == "operations-mcp unavailable"
    assert result.events[-1].event_type == "investigation.failed"


def test_coordinator_exhausts_configured_query_limit() -> None:
    result = InvestigationCoordinator(query=lambda request: EvidenceQueryResult(
        provider=request.provider, evidence_gaps=("more",)
    ), max_queries=1).run(
        _context(),
        plan=InvestigationPlan(initial_queries=(EvidenceQuery(provider="incident-mcp", question="incident"),)),
        follow_up=lambda gaps: (EvidenceQuery(provider="operations-mcp", question="more"),),
    )

    assert result.stop_reason == "limit-exhausted"
    assert len(result.events) == 4


def _context() -> InvestigationContext:
    return InvestigationContext(incident_id=uuid.uuid4(), investigation_run_id=uuid.uuid4())


def _citation(context: InvestigationContext, provider: str) -> EvidenceCitation:
    return EvidenceCitation(
        provider=provider,  # type: ignore[arg-type]
        incident_id=context.incident_id,
        investigation_run_id=context.investigation_run_id,
        evidence_type="ticket",
        evidence_id=uuid.uuid4(),
    )
