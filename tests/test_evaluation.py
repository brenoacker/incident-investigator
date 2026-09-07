from __future__ import annotations

from incident_investigation_harness.evaluation import (
    EVALUATED_SCENARIOS,
    evidence_set_for,
    request_for,
)
from incident_investigation_harness.scenarios import ScenarioName


def test_minimum_evaluation_suite_has_three_non_action_scenarios() -> None:
    assert EVALUATED_SCENARIOS == (
        ScenarioName.RETRY_STORM,
        ScenarioName.AMBIGUOUS_EVIDENCE,
        ScenarioName.PROMPT_INJECTION,
    )


def test_repeated_evaluation_uses_new_run_identity_and_scoped_evidence() -> None:
    first = request_for(ScenarioName.RETRY_STORM, 1)
    second = request_for(ScenarioName.RETRY_STORM, 2)

    assert first.incident_id == second.incident_id
    assert first.investigation_run_id != second.investigation_run_id

    evidence = evidence_set_for(second)
    assert evidence.citations
    assert {citation.investigation_run_id for citation in evidence.citations} == {
        second.investigation_run_id
    }
    assert {citation.incident_id for citation in evidence.citations} == {
        second.incident_id
    }


def test_ambiguous_evaluation_exposes_only_its_authorized_providers() -> None:
    request = request_for(ScenarioName.AMBIGUOUS_EVIDENCE, 1)
    evidence = evidence_set_for(request)

    assert {citation.provider for citation in evidence.citations} == {
        "incident-mcp",
        "operations-mcp",
    }
