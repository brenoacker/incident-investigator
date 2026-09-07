"""Public orchestration boundary for one evaluated Investigation Run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.isolation import (InvestigationEnvironment,
                                                      InvestigationSandbox,
                                                      IsolationProbeResult)
from incident_investigation_harness.quality_gate import (EvidenceSet,
                                                         IncidentOracle,
                                                         QualityGate,
                                                         QualityGateResult,
                                                         RetryStormOracle)
from incident_investigation_harness.report import InvestigationReport
from incident_investigation_harness.scenarios import ScenarioName


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

    def __init__(self, message: str, events: tuple[InvestigationEvent, ...] = ()) -> None:
        super().__init__(message)
        self.events = events


class InvestigatorAdapter(Protocol):
    """The narrow capability granted to the investigation process."""

    def investigate(
        self, request: EvaluatedRunRequest, environment: InvestigationEnvironment
    ) -> InvestigatorExecution: ...


class ExecutionFailure(BaseModel):
    """A failure to produce investigation output, never a Quality Gate verdict."""

    model_config = ConfigDict(frozen=True)

    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


@dataclass(frozen=True)
class EvaluatedRunResult:
    """Auditable output from a run, including either evaluation or execution failure."""

    request: EvaluatedRunRequest
    report: InvestigationReport | None
    events: tuple[InvestigationEvent, ...]
    quality_gate: QualityGateResult | None
    execution_failure: ExecutionFailure | None
    isolation_probes: tuple[IsolationProbeResult, ...]

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
    ) -> None:
        if evidence_set is not None and evidence_set_factory is not None:
            raise ValueError("provide evidence_set or evidence_set_factory, not both")
        self._investigator = investigator
        self._evidence_set = evidence_set
        self._evidence_set_factory = evidence_set_factory
        self._oracle = oracle or IncidentOracle()
        self._sandbox = sandbox or InvestigationSandbox()

    def run(self, request: EvaluatedRunRequest) -> EvaluatedRunResult:
        """Execute one run; investigator errors are explicit and never evaluated."""
        try:
            environment = self._sandbox.prepare(request.context)
            execution = self._investigator.investigate(request, environment)
            events = _validate_events(execution.events, request)
            evidence_set = self._get_evidence_set(request)
            quality_gate = QualityGate.evaluate(
                execution.report, evidence_set, self._get_oracle(request)
            )
        except InvestigatorExecutionFailure as error:
            try:
                events = _validate_events(error.events, request)
            except ValueError:
                events = ()
            return EvaluatedRunResult(
                request=request,
                report=None,
                events=events,
                quality_gate=None,
                execution_failure=ExecutionFailure(
                    error_type=type(error).__name__, message=str(error) or "unknown error"
                ),
                isolation_probes=(),
            )
        except InvestigatorExecutionFailure as error:
            try:
                events = _validate_events(error.events, request)
            except ValueError:
                events = ()
            return EvaluatedRunResult(
                request=request,
                report=None,
                events=events,
                quality_gate=None,
                execution_failure=ExecutionFailure(
                    error_type=type(error).__name__, message=str(error) or "unknown error"
                ),
                isolation_probes=(),
            )
        except Exception as error:  # boundary converts adapter failures to a result
            return EvaluatedRunResult(
                request=request,
                report=None,
                events=(),
                quality_gate=None,
                execution_failure=ExecutionFailure(
                    error_type=type(error).__name__, message=str(error) or "unknown error"
                ),
                isolation_probes=(),
            )
        return EvaluatedRunResult(
            request=request,
            report=execution.report,
            events=events,
            quality_gate=quality_gate,
            execution_failure=None,
            isolation_probes=environment.isolation_probes,
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

    def _get_oracle(self, request: EvaluatedRunRequest) -> IncidentOracle:
        if self._oracle is not None:
            return self._oracle
        if request.scenario == ScenarioName.RETRY_STORM:
            return RetryStormOracle()
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
