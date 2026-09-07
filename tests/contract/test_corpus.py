from __future__ import annotations

import json

import pytest

from incident_investigation_harness.corpus import (
    CORPUS_VERSION,
    CorpusCase,
    CorpusScenario,
    EvaluationCorpus,
    CorpusRunner,
    default_corpus,
)
from incident_investigation_harness.scenarios import ScenarioName


def test_default_corpus_describes_three_versioned_investigation_modes() -> None:
    corpus = default_corpus()

    assert corpus.version == CORPUS_VERSION
    assert [scenario.name for scenario in corpus.scenarios] == [
        ScenarioName.RETRY_STORM,
        ScenarioName.AMBIGUOUS_EVIDENCE,
        ScenarioName.PROMPT_INJECTION,
    ]
    assert all(scenario.version for scenario in corpus.scenarios)
    assert all(scenario.fixture_id for scenario in corpus.scenarios)
    assert all(scenario.expected_evidence_providers for scenario in corpus.scenarios)
    assert all(scenario.expected_evidence_shape for scenario in corpus.scenarios)
    assert all(scenario.expected_evidence_types for scenario in corpus.scenarios)
    assert {case.expected_verdict for case in corpus.cases} >= {
        "approved",
        "rejected",
        "execution-failure",
    }


def test_corpus_runner_executes_and_persists_an_approved_case(tmp_path) -> None:
    result = CorpusRunner(output_dir=tmp_path).run("retry-storm-approved", execution_number=1)

    assert result.verdict == "approved"
    assert result.investigator_version
    assert result.report is not None
    assert result.report.incident_id == result.request.incident_id
    assert result.artifact_directory is not None
    assert (result.artifact_directory / "report.json").exists()
    assert (result.artifact_directory / "events.jsonl").exists()
    persisted = json.loads((result.artifact_directory / "result.json").read_text())
    assert persisted["scenario_version"] == result.scenario_version
    assert persisted["oracle_version"] == "retry-storm-1"
    assert persisted["investigator_version"] == result.investigator_version
    assert persisted["incident_id"] == str(result.request.incident_id)
    assert persisted["investigation_run_id"] == str(result.request.investigation_run_id)
    assert persisted["quality_gate"]["verdict"] == "approved"
    assert "incident oracle" not in json.dumps(persisted).casefold()


def test_repeating_deterministic_case_produces_equivalent_verdict_and_evidence(tmp_path) -> None:
    runner = CorpusRunner(output_dir=tmp_path)
    first = runner.run("retry-storm-approved", execution_number=2)
    second = CorpusRunner(output_dir=tmp_path / "second").run(
        "retry-storm-approved", execution_number=2
    )

    assert first.evidence_fingerprint == second.evidence_fingerprint
    assert first.verdict == second.verdict
    assert first.request == second.request


def test_report_and_citation_mutations_change_the_approved_verdict() -> None:
    runner = CorpusRunner()
    approved = runner.run("retry-storm-approved", execution_number=5)
    unsupported = runner.run("retry-storm-unsupported-claim", execution_number=5)
    invalid_citation = runner.run("retry-storm-invalid-citation", execution_number=5)

    assert approved.verdict == "approved"
    assert unsupported.verdict == "rejected"
    assert invalid_citation.verdict == "rejected"


@pytest.mark.parametrize(
    ("case_id", "reason"),
    [
        ("retry-storm-unsupported-claim", "unsupported-factual-claim"),
        ("retry-storm-invalid-citation", "citation-not-in-evidence-set"),
        ("ambiguous-evidence-incompatible-conclusion", "incompatible-conclusion"),
    ],
)
def test_corpus_cases_cover_report_and_citation_mutations(case_id: str, reason: str) -> None:
    result = CorpusRunner().run(case_id, execution_number=3)

    assert result.verdict == "rejected"
    assert result.quality_gate is not None
    assert reason in {item.code for item in result.quality_gate.reasons}


def test_corpus_case_covers_execution_failure() -> None:
    result = CorpusRunner().run("prompt-injection-execution-failure", execution_number=4)

    assert result.verdict == "execution-failure"
    assert result.execution_failure is not None
    assert result.execution_failure.category == "cli-interrupted"


def test_prompt_injection_corpus_includes_a_grounded_read_only_approval() -> None:
    result = CorpusRunner().run("prompt-injection-approved", execution_number=4)

    assert result.verdict == "approved"
    assert result.quality_gate is not None
    assert result.quality_gate.reasons == ()
    assert result.report is not None
    report_text = json.dumps(result.report.model_dump(mode="json")).casefold()
    assert "ignore previous instructions" not in report_text
    assert "execute" not in report_text


def test_corpus_rejects_unknown_case() -> None:
    with pytest.raises(KeyError, match="unknown corpus case"):
        CorpusRunner().run("missing", execution_number=1)


def test_corpus_enforces_fixture_identity() -> None:
    corpus = default_corpus()
    scenario = corpus.scenarios[0]
    mismatched = EvaluationCorpus(
        version=corpus.version,
        scenarios=(CorpusScenario(
            name=scenario.name,
            version=scenario.version,
            fixture_id="missing-fixture",
            expected_evidence_providers=scenario.expected_evidence_providers,
            expected_evidence_types=scenario.expected_evidence_types,
            oracle_version=scenario.oracle_version,
        ), *corpus.scenarios[1:]),
        cases=corpus.cases,
    )

    with pytest.raises(ValueError, match="unknown corpus fixture"):
        CorpusRunner(corpus=mismatched).run("retry-storm-approved")


def test_corpus_enforces_expected_verdict() -> None:
    corpus = default_corpus()
    mismatched = EvaluationCorpus(
        version=corpus.version,
        scenarios=corpus.scenarios,
        cases=(CorpusCase(
            case_id="retry-storm-approved",
            scenario=ScenarioName.RETRY_STORM,
            expected_verdict="rejected",
            description="deliberately mismatched expectation",
        ), *corpus.cases[1:]),
    )

    with pytest.raises(ValueError, match="expected rejected, observed approved"):
        CorpusRunner(corpus=mismatched).run("retry-storm-approved")
