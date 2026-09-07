from incident_investigation_harness.scenarios import (
    HealthyScenario,
    RetryStormScenario,
    ScenarioName,
    compare_scenarios,
)


def test_retry_storm_amplifies_attempts_and_backlog() -> None:
    snapshot = RetryStormScenario().run()

    assert snapshot.scenario is ScenarioName.RETRY_STORM
    assert snapshot.rate_limited_attempts > 0
    assert snapshot.total_attempts >= snapshot.rate_limited_attempts
    assert snapshot.max_attempts_per_request > 1
    assert snapshot.final_backlog > snapshot.initial_backlog
    assert snapshot.peak_backlog >= snapshot.final_backlog


def test_healthy_scenario_provides_operational_reference() -> None:
    snapshot = HealthyScenario().run()

    assert snapshot.scenario is ScenarioName.HEALTHY_REFERENCE
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


def test_scenarios_publish_separate_latency_measurements() -> None:
    reference = HealthyScenario().run()
    retry_storm = RetryStormScenario().run()

    assert reference.latency.operation == "notification-processing"
    assert retry_storm.latency.operation == "notification-processing"
    assert reference.latency.window == "8 traffic rounds"
    assert retry_storm.latency.window == reference.latency.window
    assert reference.latency.sample_count > 0
    assert retry_storm.latency.sample_count > 0
    assert reference.latency.samples != retry_storm.latency.samples


def test_comparison_identifies_p99_degradation_without_matching_run_duration() -> None:
    comparison = compare_scenarios(HealthyScenario().run(), RetryStormScenario().run())

    assert comparison.reference.scenario is ScenarioName.HEALTHY_REFERENCE
    assert comparison.retry_storm.scenario is ScenarioName.RETRY_STORM
    assert comparison.degradation_threshold_percent == 25.0
    assert comparison.p99_degradation_percent >= comparison.degradation_threshold_percent
    assert comparison.is_degraded is True


def test_comparison_does_not_mark_improvement_as_degradation() -> None:
    reference = HealthyScenario().run()
    retry_storm = RetryStormScenario().run()
    lower_latency_retry_storm = retry_storm.model_copy(
        update={
            "latency": retry_storm.latency.model_copy(
                update={"p99": reference.latency.p99 / 2}
            )
        }
    )

    comparison = compare_scenarios(reference, lower_latency_retry_storm)

    assert comparison.p99_degradation_percent < 0
    assert comparison.is_degraded is False
