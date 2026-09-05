from incident_investigation_harness.scenarios import (
    HealthyScenario,
    RetryStormScenario,
)


def test_retry_storm_amplifies_attempts_and_backlog() -> None:
    snapshot = RetryStormScenario().run()

    assert snapshot.scenario == "retry-storm"
    assert snapshot.rate_limited_attempts > 0
    assert snapshot.total_attempts >= snapshot.rate_limited_attempts
    assert snapshot.max_attempts_per_request > 1
    assert snapshot.final_backlog > snapshot.initial_backlog
    assert snapshot.peak_backlog >= snapshot.final_backlog


def test_healthy_scenario_provides_operational_reference() -> None:
    snapshot = HealthyScenario().run()

    assert snapshot.scenario == "healthy-reference"
    assert snapshot.rate_limited_attempts == 0
    assert snapshot.total_attempts == snapshot.request_count
    assert snapshot.max_attempts_per_request == 1
    assert snapshot.final_backlog == 0


def test_scenario_reset_discards_previous_execution_state() -> None:
    scenario = RetryStormScenario()
    first = scenario.run()
    assert scenario.snapshot == first

    scenario.reset()
    assert scenario.snapshot is None
    second = scenario.run()

    assert second.execution_number == first.execution_number + 1
    assert second.total_attempts == first.total_attempts
    assert second.initial_backlog == 0
