from __future__ import annotations

import json
from pathlib import Path
import subprocess
import uuid

from incident_investigation_harness.adapters.codex import CodexInvestigatorAdapter
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.fixtures import AmbiguousEvidenceFixture
from incident_investigation_harness.isolation import (
    InvestigationEnvironment,
    InvestigationSandbox,
)
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
        def investigate(
            self, received: EvaluatedRunRequest, environment: InvestigationEnvironment
        ) -> InvestigatorExecution:
            assert received == request
            assert environment.context == received.context
            assert environment.allowed_evidence_providers == (
                "operations-mcp",
                "source-mcp",
            )
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
        sandbox=InvestigationSandbox(
            allowed_evidence_providers=("operations-mcp", "source-mcp")
        ),
    ).run(request)

    assert result.request == request
    assert result.report == report
    assert result.quality_gate is not None
    assert result.quality_gate.approved
    assert result.execution_failure is None
    assert result.isolation_probes
    assert all(not probe.allowed for probe in result.isolation_probes)
    assert '"investigation_run_id":"' in result.events_jsonl


def test_investigator_failure_is_not_quality_rejection_or_approval() -> None:
    class FailingInvestigator:
        def investigate(
            self, request: EvaluatedRunRequest, environment: InvestigationEnvironment
        ) -> InvestigatorExecution:
            del environment
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
        def investigate(
            self, received: EvaluatedRunRequest, environment: InvestigationEnvironment
        ) -> InvestigatorExecution:
            del environment
            return InvestigatorExecution(report=_report(received, citation))

    result = EvaluatedRunRunner(
        ControlledInvestigator(),
        evidence_set=EvidenceSet(context=request.context, citations=frozenset()),
    ).run(request)

    assert result.verdict == "rejected"
    assert result.quality_gate is not None
    assert not result.quality_gate.approved
    assert result.execution_failure is None


def test_runner_approves_an_ambiguous_run_with_calibrated_uncertainty() -> None:
    request = _request(scenario=ScenarioName.AMBIGUOUS_EVIDENCE)
    fixture = AmbiguousEvidenceFixture.for_request(request)

    class ControlledInvestigator:
        def investigate(
            self, received: EvaluatedRunRequest, environment: InvestigationEnvironment
        ) -> InvestigatorExecution:
            assert environment.allowed_evidence_providers == (
                "incident-mcp",
                "operations-mcp",
            )
            assert environment.can_write is False
            assert environment.can_administer is False
            assert environment.can_inject_failures is False
            assert environment.can_evaluate is False
            citation = next(iter(fixture.citations))
            return InvestigatorExecution(
                report=InvestigationReport(
                    schema_version="1.0",
                    incident_id=received.incident_id,
                    investigation_run_id=received.investigation_run_id,
                    impact="Some notifications were delayed.",
                    timeline=(),
                    factual_claims=(FactualClaim(
                        id="claim-1",
                        statement="The provider returned a rate-limit response.",
                        citations=(citation,),
                    ),),
                    hypotheses=(
                        {"statement": "A dependency rate limit may be involved."},
                        {"statement": "Queue contention is a plausible alternative."},
                    ),
                    confidence={"level": "low", "rationale": "The evidence is insufficient."},
                    suggested_mitigation={
                        "action": "Collect provider response logs.",
                        "rationale": "They are the next relevant evidence.",
                    },
                    evidence_gaps=({
                        "description": "Worker retry behavior is unknown.",
                        "needed_evidence": "Worker retry logs",
                    },),
                )
            )

    result = EvaluatedRunRunner(
        ControlledInvestigator(),
        evidence_set_factory=lambda run: AmbiguousEvidenceFixture.for_request(
            run
        ).evidence_set,
    ).run(request)

    assert result.approved
    assert result.report is not None
    assert result.report.probable_cause is None
    assert result.execution_failure is None


def test_runner_executes_ambiguous_report_through_codex_adapter() -> None:
    request = _request(scenario=ScenarioName.AMBIGUOUS_EVIDENCE)
    fixture = AmbiguousEvidenceFixture.for_request(request)
    captured: dict[str, object] = {}
    citation = next(iter(fixture.citations))
    report = InvestigationReport(
        schema_version="1.0",
        incident_id=request.incident_id,
        investigation_run_id=request.investigation_run_id,
        impact="Some notifications were delayed.",
        timeline=(),
        factual_claims=(FactualClaim(
            id="claim-1", statement="The provider returned a rate-limit response.", citations=(citation,)
        ),),
        hypotheses=(
            {"statement": "A dependency rate limit may be involved."},
            {"statement": "Queue contention is a plausible alternative."},
        ),
        confidence={"level": "low", "rationale": "The evidence is insufficient."},
        suggested_mitigation={"action": "Collect provider response logs.", "rationale": "They are relevant."},
        evidence_gaps=({"description": "Retry behavior is unknown.", "needed_evidence": "Worker retry logs"},),
    )

    def controlled_cli(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({
                "type": "mcp_tool_call",
                "server": citation.provider,
                "arguments": {
                    "incident_id": str(request.incident_id),
                    "investigation_run_id": str(request.investigation_run_id),
                },
            }),
            stderr="",
        )

    result = EvaluatedRunRunner(
        CodexInvestigatorAdapter(
            {
                "incident-mcp": "http://incident.test/mcp",
                "operations-mcp": "http://operations.test/mcp",
                "knowledge-mcp": "http://knowledge.test/mcp",
            },
            command_runner=controlled_cli,
        ),
        evidence_set_factory=lambda run: AmbiguousEvidenceFixture.for_request(
            run
        ).evidence_set,
    ).run(request)

    command = captured["command"]
    assert result.approved
    assert isinstance(command, list)
    assert "--sandbox" in command and "read-only" in command
    assert any("mcp_servers.incident-mcp" in item for item in command)
    assert any("mcp_servers.operations-mcp" in item for item in command)
    assert all("knowledge-mcp" not in item and "source-mcp" not in item for item in command)


def test_runner_rejects_events_from_another_run_without_evaluating_report() -> None:
    request = _request()

    class MisbehavingInvestigator:
        def investigate(
            self, received: EvaluatedRunRequest, environment: InvestigationEnvironment
        ) -> InvestigatorExecution:
            del environment
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


def _request(
    *, scenario: ScenarioName = ScenarioName.RETRY_STORM
) -> EvaluatedRunRequest:
    return EvaluatedRunRequest(
        scenario=scenario,
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
