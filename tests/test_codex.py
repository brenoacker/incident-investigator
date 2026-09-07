from __future__ import annotations

import json
import uuid
from pathlib import Path
import subprocess

import pytest

from incident_investigation_harness.adapters.codex import CodexInvestigatorAdapter, _query_provider
from incident_investigation_harness.isolation import InvestigationSandbox
from incident_investigation_harness.report import InvestigationReport
from incident_investigation_harness.runner import (
    EvaluatedRunRequest,
    EvaluatedRunRunner,
)
from incident_investigation_harness.scenarios import ScenarioName


def test_codex_adapter_hands_off_exact_context_and_allowlisted_mcp_config() -> None:
    request = _request()
    captured: dict[str, object] = {}

    def controlled_cli(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["prompt"] = kwargs["input"]
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps(_report(request).model_dump(mode="json")), encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "type": "mcp_tool_call",
                    "server": "incident-mcp",
                    "name": "query_incident_evidence",
                    "arguments": {
                        "incident_id": str(request.incident_id),
                        "investigation_run_id": str(request.investigation_run_id),
                    },
                }
            ),
            stderr="",
        )

    execution = CodexInvestigatorAdapter(
        {"incident-mcp": "http://incident.test/mcp", "operations-mcp": "http://ops.test/mcp"},
        command_runner=controlled_cli,
    ).investigate(
        request,
        InvestigationSandbox(allowed_evidence_providers=("incident-mcp",)).prepare(
            request.context
        ),
    )

    prompt = str(captured["prompt"])
    command = captured["command"]
    assert str(request.incident_id) in prompt
    assert str(request.investigation_run_id) in prompt
    assert "incident-mcp" in prompt
    assert any("incident-mcp" in item for item in command)
    assert all("operations-mcp" not in item for item in command)
    assert execution.report == _report(request)
    assert {event.event_type for event in execution.events} == {
        "investigation.started",
        "investigation.query",
        "investigation.output",
        "investigation.completed",
    }
    query = next(event for event in execution.events if event.event_type == "investigation.query")
    assert query.payload["event"]["arguments"] == {
        "incident_id": str(request.incident_id),
        "investigation_run_id": str(request.investigation_run_id),
    }
    assert all(event.investigation_run_id == request.investigation_run_id for event in execution.events)


def test_runner_reports_missing_codex_output_as_execution_failure() -> None:
    request = _request()

    def no_output(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = EvaluatedRunRunner(
        CodexInvestigatorAdapter({"incident-mcp": "http://incident.test/mcp"}, command_runner=no_output),
        sandbox=InvestigationSandbox(allowed_evidence_providers=("incident-mcp",)),
    ).run(request)

    assert result.verdict == "execution-failure"
    assert result.execution_failure is not None
    assert result.execution_failure.category == "report-missing"
    assert "no report output" in result.execution_failure.message
    assert [event.event_type for event in result.events] == [
        "investigation.started",
        "investigation.failed",
    ]


def test_codex_rejects_mcp_query_with_wrong_run_identifiers() -> None:
    request = _request()

    def wrong_query(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "type": "mcp_tool_call",
                    "arguments": {
                        "incident_id": str(request.incident_id),
                        "investigation_run_id": str(uuid.uuid4()),
                    },
                }
            ),
            stderr="",
        )

    result = EvaluatedRunRunner(
        CodexInvestigatorAdapter({"incident-mcp": "http://incident.test/mcp"}, command_runner=wrong_query),
        sandbox=InvestigationSandbox(allowed_evidence_providers=("incident-mcp",)),
    ).run(request)

    assert result.execution_failure is not None
    assert "another Investigation Run" in result.execution_failure.message


def test_codex_rejects_invalid_report_output() -> None:
    request = _request()

    def invalid_output(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(command[command.index("--output-last-message") + 1]).write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = EvaluatedRunRunner(
        CodexInvestigatorAdapter({"incident-mcp": "http://incident.test/mcp"}, command_runner=invalid_output),
        sandbox=InvestigationSandbox(allowed_evidence_providers=("incident-mcp",)),
    ).run(request)

    assert result.execution_failure is not None
    assert result.execution_failure.category == "invalid-output"
    assert "invalid Codex report" in result.execution_failure.message


def test_codex_reports_cli_exit_failure() -> None:
    request = _request()

    def failed_cli(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="failed")

    result = EvaluatedRunRunner(
        CodexInvestigatorAdapter({"incident-mcp": "http://incident.test/mcp"}, command_runner=failed_cli),
        sandbox=InvestigationSandbox(allowed_evidence_providers=("incident-mcp",)),
    ).run(request)

    assert result.execution_failure is not None
    assert result.execution_failure.category == "cli-interrupted"
    assert "status 7" in result.execution_failure.message
    assert result.events[-1].event_type == "investigation.failed"


def test_codex_reports_unavailable_provider_as_execution_failure() -> None:
    request = _request()
    result = EvaluatedRunRunner(
        CodexInvestigatorAdapter({}, command_runner=lambda *args, **kwargs: pytest.fail("CLI must not start")),
    ).run(request)

    assert result.execution_failure is not None
    assert result.execution_failure.category == "provider-unavailable"
    assert not result.approved


def test_codex_rejects_mcp_event_without_query_arguments() -> None:
    request = _request()

    def malformed_cli(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"type": "mcp_tool_call", "server": "incident-mcp"}),
            stderr="",
        )

    result = EvaluatedRunRunner(
        CodexInvestigatorAdapter({"incident-mcp": "http://incident.test/mcp"}, command_runner=malformed_cli),
        sandbox=InvestigationSandbox(allowed_evidence_providers=("incident-mcp",)),
    ).run(request)

    assert result.execution_failure is not None
    assert "omitted run-scoped identifiers" in result.execution_failure.message


def test_codex_provider_detection_handles_cli_event_shapes() -> None:
    assert _query_provider({"server_name": "operations-mcp"}) == "operations-mcp"
    assert _query_provider({"item": {"name": "query_source_evidence"}}) == "source-mcp"
    assert _query_provider({"item": {"server": "knowledge-mcp"}}) == "knowledge-mcp"
    assert _query_provider({"name": "unrelated_tool"}) is None


def _request() -> EvaluatedRunRequest:
    return EvaluatedRunRequest(
        scenario=ScenarioName.RETRY_STORM,
        incident_id=uuid.uuid4(),
        investigation_run_id=uuid.uuid4(),
    )


def _report(request: EvaluatedRunRequest) -> InvestigationReport:
    return InvestigationReport(
        schema_version="1.0",
        incident_id=request.incident_id,
        investigation_run_id=request.investigation_run_id,
        impact="Unknown.",
        timeline=(),
        factual_claims=(),
        hypotheses=(),
        confidence={"level": "low", "rationale": "Evidence is not available in this test."},
        suggested_mitigation={"action": "Collect evidence.", "rationale": "The run is controlled."},
        evidence_gaps=(),
    )
