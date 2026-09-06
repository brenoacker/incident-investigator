from __future__ import annotations

import uuid

from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.quality_gate import EvidenceSet, IncidentOracle
from incident_investigation_harness.report import (
    Confidence,
    FactualClaim,
    InvestigationReport,
)
from incident_investigation_harness.runner import (
    EvaluatedRunRequest,
    EvaluatedRunRunner,
    InvestigationEvent,
    InvestigatorExecution,
)
from incident_investigation_harness.scenarios import ScenarioName


def test_runner_exposes_report_events_and_quality_gate_result_at_public_boundary() -> None:
    request = _request()
    citation = EvidenceCitation(
        provider="operations-mcp",
        incident_id=request.incident_id,
        investigation_run_id=request.investigation_run_id,
        evidence_type="operational-log",
        evidence_id=uuid.uuid4(),
    )
    report = _report(request, citation)

    class ControlledInvestigator:
        def investigate(self, received: EvaluatedRunRequest) -> InvestigatorExecution:
            assert received == request
            return InvestigatorExecution(
                report=report,
                events=(
                    InvestigationEvent(
                        event_type="investigation.completed",
                        incident_id=received.incident_id,
                        investigation_run_id=received.investigation_run_id,
                        payload={"claims": 1},
                    ),
                ),
            )

    result = EvaluatedRunRunner(
        ControlledInvestigator(),
        evidence_set=EvidenceSet(
            context=request.context,
            citations=frozenset({citation}),
            resolvers=(Resolver(citation),),
        ),
        oracle=IncidentOracle(),
    ).run(request)

    assert result.request == request
    assert result.report == report
    assert result.quality_gate is not None
    assert result.quality_gate.approved
    assert result.execution_failure is None
    assert '"investigation_run_id":"' in result.events_jsonl


def test_investigator_failure_is_not_quality_rejection_or_approval() -> None:
    class FailingInvestigator:
        def investigate(self, request: EvaluatedRunRequest) -> InvestigatorExecution:
            raise RuntimeError("Codex stopped")

    result = EvaluatedRunRunner(FailingInvestigator()).run(_request())

    assert result.verdict == "execution-failure"
    assert not result.approved
    assert result.quality_gate is None
    assert result.execution_failure is not None
    assert result.execution_failure.message == "Codex stopped"


def test_quality_rejection_is_distinct_from_investigator_failure() -> None:
    request = _request()
    citation = EvidenceCitation(
        provider="operations-mcp",
        incident_id=request.incident_id,
        investigation_run_id=request.investigation_run_id,
        evidence_type="operational-log",
        evidence_id=uuid.uuid4(),
    )

    class ControlledInvestigator:
        def investigate(self, received: EvaluatedRunRequest) -> InvestigatorExecution:
            return InvestigatorExecution(report=_report(received, citation))

    result = EvaluatedRunRunner(
        ControlledInvestigator(),
        evidence_set=EvidenceSet(context=request.context, citations=frozenset()),
    ).run(request)

    assert result.verdict == "rejected"
    assert result.quality_gate is not None
    assert not result.quality_gate.approved
    assert result.execution_failure is None


def test_runner_rejects_events_from_another_run_without_evaluating_report() -> None:
    request = _request()

    class MisbehavingInvestigator:
        def investigate(self, received: EvaluatedRunRequest) -> InvestigatorExecution:
            return InvestigatorExecution(
                report=_report(received),
                events=(
                    InvestigationEvent(
                        event_type="bad.event",
                        incident_id=received.incident_id,
                        investigation_run_id=uuid.uuid4(),
                    ),
                ),
            )

    result = EvaluatedRunRunner(MisbehavingInvestigator()).run(request)

    assert result.execution_failure is not None
    assert result.quality_gate is None


def _request() -> EvaluatedRunRequest:
    return EvaluatedRunRequest(
        scenario=ScenarioName.RETRY_STORM,
        incident_id=uuid.uuid4(),
        investigation_run_id=uuid.uuid4(),
    )


def _report(
    request: EvaluatedRunRequest, citation: EvidenceCitation | None = None
) -> InvestigationReport:
    return InvestigationReport(
        schema_version="1.0",
        incident_id=request.incident_id,
        investigation_run_id=request.investigation_run_id,
        impact="Notifications were delayed.",
        timeline=(),
        factual_claims=(
            FactualClaim(
                id="claim-1",
                statement="The provider returned 429 responses.",
                citations=(citation,),
            ),
        )
        if citation
        else (),
        hypotheses=(),
        confidence=Confidence(level="low", rationale="Evidence is limited."),
        suggested_mitigation={"action": "Investigate", "rationale": "Collect evidence."},
        evidence_gaps=(),
    )


class Resolver:
    def __init__(self, citation: EvidenceCitation) -> None:
        self.citation = citation

    def resolve(self, citation: EvidenceCitation) -> EvidenceCitation | None:
        return citation if citation == self.citation else None
