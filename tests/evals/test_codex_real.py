from __future__ import annotations

import os
import uuid

import pytest

from incident_investigation_harness.adapters.codex import CodexInvestigatorAdapter
from incident_investigation_harness.isolation import InvestigationSandbox
from incident_investigation_harness.runner import EvaluatedRunRequest
from incident_investigation_harness.scenarios import ScenarioName


@pytest.mark.eval
def test_real_codex_cli_queries_incident_mcp_when_opted_in() -> None:
    if os.environ.get("RUN_CODEX_EVAL") != "1":
        pytest.skip("set RUN_CODEX_EVAL=1 with Codex auth and incident-mcp running")

    request = EvaluatedRunRequest(
        scenario=ScenarioName.RETRY_STORM,
        incident_id=uuid.uuid4(),
        investigation_run_id=uuid.uuid4(),
    )
    execution = CodexInvestigatorAdapter(
        {"incident-mcp": os.environ.get("INCIDENT_MCP_URL", "http://localhost:8001/mcp")}
    ).investigate(
        request,
        InvestigationSandbox(allowed_evidence_providers=("incident-mcp",)).prepare(
            request.context
        ),
    )

    assert execution.report.incident_id == request.incident_id
    assert execution.report.investigation_run_id == request.investigation_run_id
    assert any(event.event_type == "investigation.query" for event in execution.events)
