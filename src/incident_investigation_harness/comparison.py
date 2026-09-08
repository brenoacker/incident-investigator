"""Run a versioned evaluation corpus against several investigator configurations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.corpus import (
    CorpusCase,
    CorpusRunResult,
    CorpusRunner,
    EvaluationCorpus,
    Fixture,
    default_corpus,
)
from incident_investigation_harness.runner import InvestigatorAdapter


@dataclass(frozen=True)
class InvestigatorConfiguration:
    """A named investigator implementation used for one comparison candidate."""

    name: str
    version: str
    factory: Callable[[CorpusCase, Fixture], InvestigatorAdapter]


LatencyMeasurement = Callable[[str, tuple[CorpusRunResult, ...]], float]


class ComparisonRequest(BaseModel):
    """Inputs that make a comparison reproducible and auditable."""

    model_config = ConfigDict(frozen=True)

    corpus_version: str = Field(min_length=1)
    configurations: tuple[str, ...] = Field(min_length=1)
    execution_number: int = Field(default=1, gt=0)
    quality_threshold: float = Field(default=1.0, ge=0, le=1)
    reference_configuration: str | None = None


Outcome = Literal["approved", "rejected", "execution-failure"]


@dataclass(frozen=True)
class CandidateResult:
    """The comparable results and measurements for one candidate."""

    configuration: str
    version: str
    runs: tuple[CorpusRunResult, ...]
    approved: int
    rejected: int
    execution_failures: int
    quality_score: float
    citation_validity: Literal["valid", "invalid", "unavailable"]
    scenario_criteria: Literal["met", "not-met", "unavailable"]
    latency_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: float | None

    @property
    def outcome_counts(self) -> dict[Outcome, int]:
        return {
            "approved": self.approved,
            "rejected": self.rejected,
            "execution-failure": self.execution_failures,
        }


class ComparisonRegression(BaseModel):
    """A deterministic quality or reference-performance regression."""

    model_config = ConfigDict(frozen=True)

    configuration: str
    reason: Literal["quality-threshold", "worse-than-reference"]
    message: str


@dataclass(frozen=True)
class ComparisonResult:
    """Comparable candidate results and the regressions found in the run."""

    request: ComparisonRequest
    corpus_version: str
    candidates: tuple[CandidateResult, ...]
    regressions: tuple[ComparisonRegression, ...]

    @property
    def has_regressions(self) -> bool:
        return bool(self.regressions)


class ComparisonRunner:
    """Execute every corpus case once per candidate with isolated run identities."""

    def __init__(
        self,
        *,
        corpus: EvaluationCorpus | None = None,
        configurations: tuple[InvestigatorConfiguration, ...],
        output_dir: Path | None = None,
        latency_measurement: LatencyMeasurement | None = None,
    ) -> None:
        self.corpus = corpus or default_corpus()
        self.configurations = configurations
        self.output_dir = output_dir
        self._latency_measurement = latency_measurement

    def run(self, request: ComparisonRequest) -> ComparisonResult:
        if request.corpus_version != self.corpus.version:
            raise ValueError(
                f"requested corpus {request.corpus_version}, observed {self.corpus.version}"
            )
        by_name = {configuration.name: configuration for configuration in self.configurations}
        if len(by_name) != len(self.configurations):
            raise ValueError("investigator configuration names must be unique")
        if len(set(request.configurations)) != len(request.configurations):
            raise ValueError("comparison configurations must be unique")
        if (
            request.reference_configuration is not None
            and request.reference_configuration not in request.configurations
        ):
            raise ValueError("reference configuration must be selected for comparison")
        missing = set(request.configurations) - set(by_name)
        if missing:
            raise ValueError(f"unknown investigator configuration: {sorted(missing)}")

        candidates = tuple(
            self._run_candidate(by_name[name], request) for name in request.configurations
        )
        regressions = self._regressions(request, candidates)
        result = ComparisonResult(
            request=request,
            corpus_version=self.corpus.version,
            candidates=candidates,
            regressions=tuple(regressions),
        )
        if self.output_dir is not None:
            self._persist(result)
        return result

    def _run_candidate(
        self, configuration: InvestigatorConfiguration, request: ComparisonRequest
    ) -> CandidateResult:
        runner = CorpusRunner(
            corpus=self.corpus,
            output_dir=None,
            investigator_version=configuration.version,
            investigator_factory=configuration.factory,
            run_identity=configuration.name,
            enforce_expected_verdict=False,
        )
        runs = tuple(
            runner.run(case.case_id, execution_number=request.execution_number)
            for case in self.corpus.cases
        )
        duration = (
            self._latency_measurement(configuration.name, runs)
            if self._latency_measurement is not None
            else sum(run.evaluated_run.duration_seconds for run in runs)
        )
        if duration < 0:
            raise ValueError("latency measurement must be non-negative")
        approved = sum(run.verdict == "approved" for run in runs)
        rejected = sum(run.verdict == "rejected" for run in runs)
        failures = sum(run.verdict == "execution-failure" for run in runs)
        gate_results = [run.quality_gate for run in runs if run.quality_gate is not None]
        reason_codes = {reason.code for gate in gate_results for reason in gate.reasons}
        completed_runs = [run for run in runs if run.verdict != "execution-failure"]
        usages = [run.evaluated_run.usage for run in completed_runs]
        citation_codes = {
            "missing-citation", "citation-not-in-evidence-set", "citation-from-other-run",
            "unresolvable-citation",
        }
        unassessable_codes = {"invalid-schema", "incompatible-run"}
        return CandidateResult(
            configuration=configuration.name,
            version=configuration.version,
            runs=runs,
            approved=approved,
            rejected=rejected,
            execution_failures=failures,
            quality_score=approved / len(runs) if runs else 0,
            citation_validity=("invalid" if reason_codes & citation_codes else
                "unavailable" if reason_codes & unassessable_codes or not gate_results else "valid"),
            scenario_criteria=("not-met" if any(code in reason_codes for code in {
                "scenario-criteria-not-met", "unsupported-factual-claim", "incompatible-conclusion", "incomplete-mitigation", "capability-boundary-violation"
            }) else "met" if gate_results else "unavailable"),
            latency_seconds=duration,
            input_tokens=_sum_usage(usages, "input_tokens"),
            output_tokens=_sum_usage(usages, "output_tokens"),
            estimated_cost=_sum_cost(usages),
        )

    @staticmethod
    def _regressions(
        request: ComparisonRequest, candidates: tuple[CandidateResult, ...]
    ) -> list[ComparisonRegression]:
        regressions: list[ComparisonRegression] = []
        for candidate in candidates:
            if candidate.quality_score < request.quality_threshold:
                regressions.append(ComparisonRegression(
                    configuration=candidate.configuration,
                    reason="quality-threshold",
                    message=f"quality score {candidate.quality_score:.3f} is below {request.quality_threshold:.3f}",
                ))
        if request.reference_configuration is not None:
            reference = next(item for item in candidates if item.configuration == request.reference_configuration)
            for candidate in candidates:
                if candidate.configuration != reference.configuration and candidate.latency_seconds > reference.latency_seconds:
                    regressions.append(ComparisonRegression(
                        configuration=candidate.configuration,
                        reason="worse-than-reference",
                        message="latency is worse than the reference configuration",
                    ))
        return regressions

    def _persist(self, result: ComparisonResult) -> None:
        assert self.output_dir is not None
        directory = self.output_dir / f"comparison-{result.request.execution_number}"
        if directory.exists():
            raise FileExistsError(f"comparison output already exists: {directory}")
        directory.mkdir(parents=True)
        (directory / "comparison.json").write_text(
            json.dumps(_result_payload(result), indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def _sum_usage(usages: Sequence[object | None], field: str) -> int | None:
    if not usages or any(usage is None for usage in usages):
        return None
    values = [getattr(usage, field) for usage in usages if usage is not None]
    return sum(values) if all(value is not None for value in values) else None


def _sum_cost(usages: Sequence[object | None]) -> float | None:
    if not usages or any(usage is None for usage in usages):
        return None
    values = [getattr(usage, "estimated_cost") for usage in usages if usage is not None]
    return sum(values) if all(value is not None for value in values) else None


def _result_payload(result: ComparisonResult) -> dict[str, object]:
    return {
        "request": result.request.model_dump(mode="json"),
        "corpus_version": result.corpus_version,
        "candidates": [
            {
                "configuration": candidate.configuration,
                "version": candidate.version,
                "outcome_counts": candidate.outcome_counts,
                "quality_score": candidate.quality_score,
                "citation_validity": candidate.citation_validity,
                "scenario_criteria": candidate.scenario_criteria,
                "latency_seconds": candidate.latency_seconds,
                "input_tokens": candidate.input_tokens,
                "output_tokens": candidate.output_tokens,
                "estimated_cost": candidate.estimated_cost,
                "runs": [
                    {
                        "case_id": run.case.case_id,
                        "scenario": run.case.scenario.value,
                        "incident_id": str(run.request.incident_id),
                        "investigation_run_id": str(run.request.investigation_run_id),
                        "verdict": run.verdict,
                    }
                    for run in candidate.runs
                ],
            }
            for candidate in result.candidates
        ],
        "regressions": [regression.model_dump(mode="json") for regression in result.regressions],
    }
