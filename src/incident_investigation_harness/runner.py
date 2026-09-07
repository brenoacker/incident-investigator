"""Public orchestration boundary for one evaluated Investigation Run."""

from __future__ import annotations

import uuid
from time import perf_counter
from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.isolation import (InvestigationEnvironment,
                                                      InvestigationSandbox,
                                                      IsolationProbeResult)
from incident_investigation_harness.quality_gate import (EvidenceSet,
                                                         AmbiguousEvidenceOracle,
                                                         IncidentOracle,
                                                         PromptInjectionOracle,
                                                         QualityGate,
                                                         QualityGateResult,
                                                         RetryStormOracle)
from incident_investigation_harness.report import InvestigationReport
from incident_investigation_harness.scenarios import ScenarioName
from incident_investigation_harness.telemetry import span, telemetry


class EvaluatedRunRequest(BaseModel):
    """The caller-supplied identity and scenario for one Investigation Run."""

    model_config = ConfigDict(frozen=True)

    scenario: ScenarioName
    incident_id: uuid.UUID
    investigation_run_id: uuid.UUID

    @property
    def context(self) -> InvestigationContext:
        return InvestigationContext(
            incident_id=self.incident_id,
            investigation_run_id=self.investigation_run_id,
        )


class InvestigationEvent(BaseModel):
    """One audit event emitted by an investigator, scoped to its run."""

    model_config = ConfigDict(frozen=True)

    event_type: str = Field(min_length=1, max_length=100)
    incident_id: uuid.UUID
    investigation_run_id: uuid.UUID
    payload: Mapping[str, object] = Field(default_factory=dict)


class InvestigatorExecution(BaseModel):
    """The report and audit events collected from an investigator."""

    model_config = ConfigDict(frozen=True)

    report: InvestigationReport
    events: tuple[InvestigationEvent, ...] = ()


class InvestigatorExecutionFailure(RuntimeError):
    """An investigator failure that still has scoped audit events to preserve."""

    def __init__(
        self,
        message: str,
        events: tuple[InvestigationEvent, ...] = (),
        *,
        category: str = "investigator-error",
    ) -> None:
        super().__init__(message)
        self.events = events
        self.category = category


class InvestigatorAdapter(Protocol):
    """The narrow capability granted to the investigation process."""

    def investigate(
        self, request: EvaluatedRunRequest, environment: InvestigationEnvironment
    ) -> InvestigatorExecution: ...


ExecutionFailureCategory = Literal[
    "provider-unavailable",
    "cli-interrupted",
    "invalid-output",
    "report-missing",
    "investigator-error",
    "runner-error",
]


class RunArtifact(BaseModel):
    """Safe, run-scoped material retained for audit and troubleshooting."""

    model_config = ConfigDict(frozen=True)

    artifact_type: Literal["events", "report", "evidence"]
    context: InvestigationContext
    payload: Mapping[str, object]


class RunArtifactStore:
    """Store artifacts by Investigation Run identity, never in one shared bucket."""

    def __init__(self) -> None:
        self._artifacts: dict[uuid.UUID, tuple[RunArtifact, ...]] = {}

    def start(self, context: InvestigationContext) -> None:
        """Begin an attempt and discard stale data for a reused run identity."""
        self._artifacts[context.investigation_run_id] = ()

    def record(self, artifact: RunArtifact) -> None:
        existing = self._artifacts.get(artifact.context.investigation_run_id)
        if existing is None or any(
            item.context != artifact.context for item in existing
        ):
            raise ValueError("artifact does not belong to an active Investigation Run")
        self._artifacts[artifact.context.investigation_run_id] = (*existing, artifact)

    def for_run(self, context: InvestigationContext) -> tuple[RunArtifact, ...]:
        """Return only artifacts belonging to this exact run context."""
        return tuple(
            artifact
            for artifact in self._artifacts.get(context.investigation_run_id, ())
            if artifact.context == context
        )


class ExecutionFailure(BaseModel):
    """A failure to produce investigation output, never a Quality Gate verdict."""

    model_config = ConfigDict(frozen=True)

    category: ExecutionFailureCategory
    cause: str = Field(min_length=1)
    artifacts: tuple[RunArtifact, ...] = ()

    @property
    def error_type(self) -> str:
        """Compatibility label for callers that used the old failure contract."""
        return self.category

    @property
    def message(self) -> str:
        """Compatibility alias for the failure cause."""
        return self.cause


@dataclass(frozen=True)
class EvaluatedRunResult:
    """Auditable output from a run, including either evaluation or execution failure."""

    request: EvaluatedRunRequest
    report: InvestigationReport | None
    events: tuple[InvestigationEvent, ...]
    quality_gate: QualityGateResult | None
    execution_failure: ExecutionFailure | None
    isolation_probes: tuple[IsolationProbeResult, ...]
    artifacts: tuple[RunArtifact, ...] = ()

    @property
    def approved(self) -> bool:
        return self.quality_gate is not None and self.quality_gate.approved

    @property
    def verdict(self) -> str:
        if self.execution_failure is not None:
            return "execution-failure"
        return self.quality_gate.verdict if self.quality_gate is not None else "execution-failure"

    @property
    def events_jsonl(self) -> str:
        """Return newline-delimited, JSON-serializable audit events."""
        return "\n".join(
            event.model_dump_json() for event in self.events
        )


EvidenceSetFactory = Callable[[EvaluatedRunRequest], EvidenceSet]


class EvaluatedRunRunner:
    """Compose preparation, investigation, artifact collection and external evaluation."""

    def __init__(
        self,
        investigator: InvestigatorAdapter,
        evidence_set: EvidenceSet | None = None,
        oracle: IncidentOracle | None = None,
        evidence_set_factory: EvidenceSetFactory | None = None,
        sandbox: InvestigationSandbox | None = None,
        artifact_store: RunArtifactStore | None = None,
    ) -> None:
        if evidence_set is not None and evidence_set_factory is not None:
            raise ValueError("provide evidence_set or evidence_set_factory, not both")
        self._investigator = investigator
        self._evidence_set = evidence_set
        self._evidence_set_factory = evidence_set_factory
        self._oracle = oracle
        self._sandbox = sandbox
        self._artifact_store = artifact_store or RunArtifactStore()

    def run(self, request: EvaluatedRunRequest) -> EvaluatedRunResult:
        """Execute one run; investigator errors are explicit and never evaluated."""
        started = perf_counter()
        telemetry.runs_started.add(1, {"scenario": request.scenario.value})
        with span(
            "evaluated-run",
            context=request.context,
            component="runner",
            operation="run",
            scenario=request.scenario.value,
        ):
            try:
                self._artifact_store.start(request.context)
                try:
                    environment = self._sandbox_for(request).prepare(request.context)
                    execution = self._investigator.investigate(request, environment)
                    events = _validate_events(execution.events, request)
                    self._artifact_store.record(_events_artifact(request.context, events))
                    self._artifact_store.record(_report_artifact(request.context, execution.report))
                    evidence_set = self._get_evidence_set(request)
                    self._artifact_store.record(_evidence_artifact(request.context, evidence_set))
                    quality_gate = QualityGate.evaluate(
                        execution.report,
                        evidence_set,
                        self._get_oracle(request),
                        events=events,
                        environment=environment,
                    )
                except InvestigatorExecutionFailure as error:
                    try:
                        events = _validate_events(error.events, request)
                    except ValueError:
                        events = ()
                    if events:
                        self._artifact_store.record(_events_artifact(request.context, events))
                    telemetry.runs_failed.add(1, {"scenario": request.scenario.value, "category": _failure_category(error.category)})
                    return EvaluatedRunResult(
                        request=request, report=None, events=events, quality_gate=None,
                        execution_failure=ExecutionFailure(
                            category=_failure_category(error.category), cause=str(error) or "unknown error",
                            artifacts=self._artifact_store.for_run(request.context),
                        ), isolation_probes=(), artifacts=self._artifact_store.for_run(request.context),
                    )
                except Exception as error:  # boundary converts adapter failures to a result
                    telemetry.runs_failed.add(1, {"scenario": request.scenario.value, "category": "runner-error"})
                    return EvaluatedRunResult(
                        request=request, report=None, events=(), quality_gate=None,
                        execution_failure=ExecutionFailure(
                            category="runner-error", cause=str(error) or "unknown error",
                            artifacts=self._artifact_store.for_run(request.context),
                        ), isolation_probes=(),
                    )
                telemetry.runs_completed.add(1, {"scenario": request.scenario.value, "verdict": quality_gate.verdict})
                return EvaluatedRunResult(
                    request=request, report=execution.report, events=events,
                    quality_gate=quality_gate, execution_failure=None,
                    isolation_probes=environment.isolation_probes,
                    artifacts=self._artifact_store.for_run(request.context),
                )
            finally:
                telemetry.run_duration.record(
                    perf_counter() - started, {"scenario": request.scenario.value}
                )

    def _get_evidence_set(self, request: EvaluatedRunRequest) -> EvidenceSet:
        if self._evidence_set_factory is not None:
            evidence_set = self._evidence_set_factory(request)
        elif self._evidence_set is not None:
            evidence_set = self._evidence_set
        else:
            evidence_set = EvidenceSet(context=request.context, citations=frozenset())
        if evidence_set.context != request.context:
            raise ValueError("EvidenceSet context does not match the evaluated run")
        return evidence_set

    def _sandbox_for(self, request: EvaluatedRunRequest) -> InvestigationSandbox:
        if self._sandbox is not None:
            return self._sandbox
        if request.scenario == ScenarioName.AMBIGUOUS_EVIDENCE:
            return InvestigationSandbox(
                allowed_evidence_providers=("incident-mcp", "operations-mcp")
            )
        return InvestigationSandbox()

    def _get_oracle(self, request: EvaluatedRunRequest) -> IncidentOracle:
        if self._oracle is not None:
            return self._oracle
        if request.scenario == ScenarioName.RETRY_STORM:
            return RetryStormOracle()
        if request.scenario == ScenarioName.AMBIGUOUS_EVIDENCE:
            return AmbiguousEvidenceOracle()
        if request.scenario == ScenarioName.PROMPT_INJECTION:
            return PromptInjectionOracle()
        return IncidentOracle()


def _validate_events(
    events: tuple[InvestigationEvent, ...], request: EvaluatedRunRequest
) -> tuple[InvestigationEvent, ...]:
    if any(
        event.incident_id != request.incident_id
        or event.investigation_run_id != request.investigation_run_id
        for event in events
    ):
        raise ValueError("investigator emitted an event for another Investigation Run")
    return events


def _failure_category(category: str) -> ExecutionFailureCategory:
    if category in {
        "provider-unavailable",
        "cli-interrupted",
        "invalid-output",
        "report-missing",
        "investigator-error",
    }:
        return category  # type: ignore[return-value]
    return "investigator-error"


def _events_artifact(
    context: InvestigationContext, events: tuple[InvestigationEvent, ...]
) -> RunArtifact:
    return RunArtifact(
        artifact_type="events",
        context=context,
        payload={"events": tuple(event.model_dump(mode="json") for event in events)},
    )


def _report_artifact(
    context: InvestigationContext, report: InvestigationReport
) -> RunArtifact:
    return RunArtifact(
        artifact_type="report", context=context, payload=report.model_dump(mode="json")
    )


def _evidence_artifact(
    context: InvestigationContext, evidence_set: EvidenceSet
) -> RunArtifact:
    return RunArtifact(
        artifact_type="evidence",
        context=context,
        payload={"citations": tuple(citation.model_dump(mode="json") for citation in evidence_set.citations)},
    )
