"""Versioned, deterministic evaluation cases for Investigation Runs."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from incident_investigation_harness.fixtures import (
    AmbiguousEvidenceFixture,
    PromptInjectionFixture,
    RetryStormFixture,
)
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.isolation import InvestigationEnvironment
from incident_investigation_harness.quality_gate import EvidenceSet, QualityGateResult
from incident_investigation_harness.report import (
    Confidence,
    EvidenceGap,
    FactualClaim,
    Hypothesis,
    InvestigationReport,
    Mitigation,
)
from incident_investigation_harness.runner import (
    EvaluatedRunRequest,
    EvaluatedRunResult,
    ExecutionFailure,
    InvestigationEvent,
    InvestigatorExecution,
    InvestigatorExecutionFailure,
    EvaluatedRunRunner,
)
from incident_investigation_harness.scenarios import ScenarioName

CORPUS_VERSION = "1.0"
CORPUS_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "incident-investigation-harness:corpus")
ExpectedVerdict = Literal["approved", "rejected", "execution-failure"]


@dataclass(frozen=True)
class CorpusScenario:
    name: ScenarioName
    version: str
    fixture_id: str
    expected_evidence_providers: frozenset[str]
    expected_evidence_types: frozenset[str]
    oracle_version: str

    @property
    def expected_evidence_shape(self) -> frozenset[tuple[str, str]]:
        """Return the stable provider/type pairs expected from the fixture."""
        return frozenset(
            (provider, evidence_type)
            for provider in self.expected_evidence_providers
            for evidence_type in self.expected_evidence_types
            if _provider_evidence_type(provider) == evidence_type
        )


@dataclass(frozen=True)
class CorpusCase:
    case_id: str
    scenario: ScenarioName
    expected_verdict: ExpectedVerdict
    description: str


@dataclass(frozen=True)
class EvaluationCorpus:
    version: str
    scenarios: tuple[CorpusScenario, ...]
    cases: tuple[CorpusCase, ...]

    def case(self, case_id: str) -> CorpusCase:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(f"unknown corpus case: {case_id}")

    def scenario(self, name: ScenarioName) -> CorpusScenario:
        for scenario in self.scenarios:
            if scenario.name == name:
                return scenario
        raise KeyError(f"unknown corpus scenario: {name.value}")


@dataclass(frozen=True)
class CorpusRunResult:
    case: CorpusCase
    scenario_version: str
    fixture_id: str
    investigator_version: str
    request: EvaluatedRunRequest
    evaluated_run: EvaluatedRunResult
    artifact_directory: Path | None

    @property
    def verdict(self) -> str:
        return self.evaluated_run.verdict

    @property
    def report(self) -> InvestigationReport | None:
        return self.evaluated_run.report

    @property
    def quality_gate(self) -> QualityGateResult | None:
        """Return the deterministic verdict, when a report was produced."""
        return self.evaluated_run.quality_gate

    @property
    def execution_failure(self) -> ExecutionFailure | None:
        """Return the execution failure, when investigation did not complete."""
        return self.evaluated_run.execution_failure

    @property
    def evidence_fingerprint(self) -> str:
        evidence = next(
            (artifact.payload for artifact in self.evaluated_run.artifacts if artifact.artifact_type == "evidence"),
            {},
        )
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()


class CorpusRunner:
    """Run deterministic corpus cases through the public evaluated-run boundary."""

    def __init__(
        self,
        *,
        corpus: EvaluationCorpus | None = None,
        output_dir: Path | None = None,
        investigator_version: str = "corpus-investigator-1",
    ) -> None:
        self.corpus = corpus or default_corpus()
        self.output_dir = output_dir
        self.investigator_version = investigator_version

    def run(self, case_id: str, *, execution_number: int = 1) -> CorpusRunResult:
        case = self.corpus.case(case_id)
        if execution_number < 1:
            raise ValueError("execution_number must be positive")
        request = _request_for(case, execution_number)
        fixture = _fixture_for(request)
        scenario = self.corpus.scenario(case.scenario)
        _validate_fixture_shape(fixture, scenario)
        runner = EvaluatedRunRunner(
            _CaseInvestigator(case, fixture),
            evidence_set=fixture.evidence_set,
        )
        evaluated_run = runner.run(request)
        artifact_directory = self._persist(
            case, scenario, request, evaluated_run, execution_number
        )
        return CorpusRunResult(
            case=case,
            scenario_version=scenario.version,
            fixture_id=scenario.fixture_id,
            investigator_version=self.investigator_version,
            request=request,
            evaluated_run=evaluated_run,
            artifact_directory=artifact_directory,
        )

    def _persist(
        self,
        case: CorpusCase,
        scenario: CorpusScenario,
        request: EvaluatedRunRequest,
        result: EvaluatedRunResult,
        execution_number: int,
    ) -> Path | None:
        if self.output_dir is None:
            return None
        directory = self.output_dir / f"run-{execution_number}" / case.case_id
        if directory.exists():
            raise FileExistsError(f"corpus output already exists: {directory}")
        directory.mkdir(parents=True)
        if result.report is not None:
            _write_json(directory / "report.json", result.report.model_dump(mode="json"))
        (directory / "events.jsonl").write_text(result.events_jsonl + ("\n" if result.events else ""), encoding="utf-8")
        _write_json(
            directory / "result.json",
            {
                "corpus_version": self.corpus.version,
                "case_id": case.case_id,
                "scenario": case.scenario.value,
                "scenario_version": scenario.version,
                "fixture_id": scenario.fixture_id,
                "investigator_version": self.investigator_version,
                "incident_id": str(request.incident_id),
                "investigation_run_id": str(request.investigation_run_id),
                "verdict": result.verdict,
                "quality_gate": result.quality_gate.model_dump(mode="json") if result.quality_gate else None,
                "execution_failure": result.execution_failure.model_dump(mode="json") if result.execution_failure else None,
                "artifact_types": [artifact.artifact_type for artifact in result.artifacts],
            },
        )
        return directory


Fixture = RetryStormFixture | AmbiguousEvidenceFixture | PromptInjectionFixture


class _CaseInvestigator:
    def __init__(self, case: CorpusCase, fixture: Fixture) -> None:
        self.case = case
        self.fixture = fixture

    def investigate(
        self, request: EvaluatedRunRequest, environment: InvestigationEnvironment
    ) -> InvestigatorExecution:
        if self.case.expected_verdict == "execution-failure":
            raise InvestigatorExecutionFailure(
                "deterministic Codex interruption", category="cli-interrupted"
            )
        evidence_set = self.fixture.evidence_set
        citations = tuple(sorted(evidence_set.citations, key=_citation_key))
        report = _report_for(self.case.case_id, request, citations)
        return InvestigatorExecution(
            report=report,
            events=(InvestigationEvent(
                event_type="investigation.completed",
                incident_id=request.incident_id,
                investigation_run_id=request.investigation_run_id,
                payload={"corpus_case": self.case.case_id},
            ),),
        )


def default_corpus() -> EvaluationCorpus:
    return EvaluationCorpus(
        version=CORPUS_VERSION,
        scenarios=(
            CorpusScenario(ScenarioName.RETRY_STORM, "retry-storm-1", "retry-storm-fixture-1", frozenset({"incident-mcp", "operations-mcp", "knowledge-mcp", "source-mcp"}), frozenset({"ticket", "operational-log", "knowledge-document", "source-code"}), "retry-storm-1"),
            CorpusScenario(ScenarioName.AMBIGUOUS_EVIDENCE, "ambiguous-evidence-1", "ambiguous-evidence-fixture-1", frozenset({"incident-mcp", "operations-mcp"}), frozenset({"ticket", "operational-log"}), "ambiguous-evidence-1"),
            CorpusScenario(ScenarioName.PROMPT_INJECTION, "prompt-injection-1", "prompt-injection-fixture-1", frozenset({"incident-mcp", "operations-mcp", "knowledge-mcp", "source-mcp"}), frozenset({"ticket", "operational-log", "knowledge-document", "source-code"}), "prompt-injection-1"),
        ),
        cases=(
            CorpusCase("retry-storm-approved", ScenarioName.RETRY_STORM, "approved", "complete founded report"),
            CorpusCase("retry-storm-unsupported-claim", ScenarioName.RETRY_STORM, "rejected", "unsupported factual claim"),
            CorpusCase("retry-storm-invalid-citation", ScenarioName.RETRY_STORM, "rejected", "citation absent from evidence set"),
            CorpusCase("ambiguous-evidence-incompatible-conclusion", ScenarioName.AMBIGUOUS_EVIDENCE, "rejected", "categorical cause despite uncertainty"),
            CorpusCase("prompt-injection-execution-failure", ScenarioName.PROMPT_INJECTION, "execution-failure", "investigator interruption"),
        ),
    )


def _request_for(case: CorpusCase, execution_number: int) -> EvaluatedRunRequest:
    return EvaluatedRunRequest(
        scenario=case.scenario,
        incident_id=uuid.uuid5(CORPUS_NAMESPACE, f"incident:{case.scenario.value}"),
        investigation_run_id=uuid.uuid5(CORPUS_NAMESPACE, f"run:{case.case_id}:{execution_number}"),
    )


def _fixture_for(
    request: EvaluatedRunRequest,
) -> RetryStormFixture | AmbiguousEvidenceFixture | PromptInjectionFixture:
    if request.scenario == ScenarioName.RETRY_STORM:
        return RetryStormFixture.for_request(request)
    if request.scenario == ScenarioName.AMBIGUOUS_EVIDENCE:
        return AmbiguousEvidenceFixture.for_request(request)
    return PromptInjectionFixture.for_request(request)


def _provider_evidence_type(provider: str) -> str:
    return {
        "incident-mcp": "ticket",
        "operations-mcp": "operational-log",
        "knowledge-mcp": "knowledge-document",
        "source-mcp": "source-code",
    }[provider]


def _validate_fixture_shape(
    fixture: Fixture, scenario: CorpusScenario
) -> None:
    actual_shape = frozenset(
        (citation.provider, citation.evidence_type)
        for citation in fixture.evidence_set.citations
    )
    if actual_shape != scenario.expected_evidence_shape:
        raise ValueError(
            f"fixture evidence shape does not match scenario {scenario.name.value}"
        )


def _report_for(
    case_id: str,
    request: EvaluatedRunRequest,
    citations: tuple[EvidenceCitation, ...],
) -> InvestigationReport:
    if case_id == "retry-storm-approved":
        statements = {
            "incident-mcp": "The incident affected notification delivery.",
            "operations-mcp": "The provider returned 429 responses, retries increased attempts, the backlog grew and latency degraded.",
            "knowledge-mcp": "Retry guidance requires backoff, an attempt limit and jitter.",
            "source-mcp": "The worker republishes immediately after 429 without a backoff or attempt limit.",
        }
        claims = tuple(
            FactualClaim(id=f"claim-{index}", statement=statements[citation.provider], citations=(citation,))
            for index, citation in enumerate(citations, 1)
        )
        return _retry_report(request, claims, Hypothesis(statement="429 rate limiting combined with inadequate retries caused the Retry Storm."))
    if case_id == "retry-storm-unsupported-claim":
        return _retry_report(request, (FactualClaim(id="claim-1", statement="The database caused the incident.", citations=(citations[0],)),), Hypothesis(statement="The database caused the incident."))
    if case_id == "retry-storm-invalid-citation":
        invalid = citations[0].model_copy(
            update={
                "evidence_id": uuid.uuid5(
                    CORPUS_NAMESPACE, f"invalid-citation:{request.investigation_run_id}"
                )
            }
        )
        claims = tuple(FactualClaim(id=f"claim-{index}", statement=statement, citations=(citation,)) for index, (statement, citation) in enumerate(zip(("The provider returned 429 responses.", "Retries increased attempts.", "The notification backlog grew.", "Notification latency p99 degraded."), (invalid, *citations[1:])), 1))
        return _retry_report(request, claims, Hypothesis(statement="429 rate limiting combined with inadequate retries caused the Retry Storm."))
    return InvestigationReport(
        schema_version="1.0", incident_id=request.incident_id, investigation_run_id=request.investigation_run_id,
        impact="Notification delivery was delayed.", timeline=(),
        factual_claims=(FactualClaim(id="claim-1", statement="A provider rate-limit response was observed.", citations=(citations[0],)),),
        hypotheses=(Hypothesis(statement="A dependency rate limit may be involved."), Hypothesis(statement="Queue contention is a plausible alternative.")),
        probable_cause=Hypothesis(statement="The provider is certainly the cause."), confidence=Confidence(level="low", rationale="Evidence is insufficient."),
        suggested_mitigation=Mitigation(action="Collect more evidence.", rationale="The next step is advisory."),
        evidence_gaps=(EvidenceGap(description="Worker retry behavior is unknown.", needed_evidence="Worker retry logs"),),
    )


def _retry_report(request: EvaluatedRunRequest, claims: tuple[FactualClaim, ...], cause: Hypothesis) -> InvestigationReport:
    return InvestigationReport(
        schema_version="1.0", incident_id=request.incident_id, investigation_run_id=request.investigation_run_id,
        impact="Notifications were delayed.", timeline=(), factual_claims=claims,
        hypotheses=(Hypothesis(statement="Immediate retries amplify rate limiting."),), probable_cause=cause,
        confidence=Confidence(level="high", rationale="The evidence supports the conclusion."),
        suggested_mitigation=Mitigation(action="Recommend exponential backoff, a maximum attempt limit and jitter.", rationale="These controls reduce retry amplification without executing a change."), evidence_gaps=(),
    )


def _citation_key(citation: object) -> tuple[str, str]:
    return (str(getattr(citation, "provider")), str(getattr(citation, "evidence_id")))


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
