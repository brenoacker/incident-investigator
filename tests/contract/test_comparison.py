from __future__ import annotations

import pytest

from incident_investigation_harness.comparison import (
    ComparisonRequest,
    ComparisonRunner,
    InvestigatorConfiguration,
)
from incident_investigation_harness.corpus import CorpusCase, Fixture, CorpusInvestigatorFake
from incident_investigation_harness.runner import InvestigatorAdapter
from incident_investigation_harness.runner import InvestigatorUsage


def _configuration(name: str, *, usage: bool = False) -> InvestigatorConfiguration:
    def factory(case: CorpusCase, fixture: Fixture) -> InvestigatorAdapter:
        fake = CorpusInvestigatorFake(case.case_id, fixture)
        if not usage:
            return fake

        class MeasuredInvestigatorFake:
            def investigate(self, request, environment):
                return fake.investigate(request, environment).model_copy(
                    update={"usage": InvestigatorUsage(input_tokens=10, output_tokens=5, estimated_cost=0.01)}
                )

        return MeasuredInvestigatorFake()

    return InvestigatorConfiguration(name=name, version=f"{name}-1", factory=factory)


def test_comparison_runs_the_same_corpus_for_two_isolated_configurations() -> None:
    runner = ComparisonRunner(configurations=(_configuration("baseline", usage=True), _configuration("candidate")))

    result = runner.run(ComparisonRequest(
        corpus_version="1.0",
        configurations=("baseline", "candidate"),
        execution_number=7,
    ))

    assert [candidate.configuration for candidate in result.candidates] == ["baseline", "candidate"]
    assert all(candidate.approved == 2 for candidate in result.candidates)
    assert all(candidate.rejected == 3 for candidate in result.candidates)
    assert all(candidate.execution_failures == 1 for candidate in result.candidates)
    assert result.candidates[0].input_tokens == 50
    assert result.candidates[0].output_tokens == 25
    assert result.candidates[0].estimated_cost == 0.05
    baseline_ids = {run.request.investigation_run_id for run in result.candidates[0].runs}
    candidate_ids = {run.request.investigation_run_id for run in result.candidates[1].runs}
    assert baseline_ids.isdisjoint(candidate_ids)
    assert [run.request.incident_id for run in result.candidates[0].runs] == [
        run.request.incident_id for run in result.candidates[1].runs
    ]


def test_comparison_reports_quality_and_reference_regressions() -> None:
    def failing_factory(case: CorpusCase, fixture: Fixture) -> InvestigatorAdapter:
        return CorpusInvestigatorFake("retry-storm-unsupported-claim", fixture)

    runner = ComparisonRunner(configurations=(
        _configuration("reference"),
        InvestigatorConfiguration("candidate", "candidate-1", failing_factory),
    ))
    result = runner.run(ComparisonRequest(
        corpus_version="1.0",
        configurations=("reference", "candidate"),
        reference_configuration="reference",
        quality_threshold=1.0,
    ))

    assert result.has_regressions
    assert any(item.configuration == "candidate" and item.reason == "quality-threshold" for item in result.regressions)


def test_comparison_reports_a_candidate_slower_than_the_reference() -> None:
    def slow_factory(case: CorpusCase, fixture: Fixture) -> InvestigatorAdapter:
        fake = CorpusInvestigatorFake(case.case_id, fixture)

        class SlowInvestigatorFake:
            def investigate(self, request, environment):
                return fake.investigate(request, environment)

        return SlowInvestigatorFake()

    result = ComparisonRunner(configurations=(
        _configuration("reference"),
        InvestigatorConfiguration("slow", "slow-1", slow_factory),
    ), latency_measurement=lambda name, runs: 2.0 if name == "slow" else 1.0).run(ComparisonRequest(
        corpus_version="1.0",
        configurations=("reference", "slow"),
        reference_configuration="reference",
    ))

    assert any(item.configuration == "slow" and item.reason == "worse-than-reference" for item in result.regressions)


def test_comparison_requires_the_reference_to_be_selected() -> None:
    with pytest.raises(ValueError, match="must be selected"):
        ComparisonRunner(configurations=(_configuration("reference"),)).run(ComparisonRequest(
            corpus_version="1.0",
            configurations=("reference",),
            reference_configuration="missing",
        ))
