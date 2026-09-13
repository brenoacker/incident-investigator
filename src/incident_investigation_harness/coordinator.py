"""Bounded, read-only orchestration for a multi-step Investigation Run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.isolation import (
    AllowedEvidenceProvider,
    InvestigationEnvironment,
)
from incident_investigation_harness.report import InvestigationReport
from incident_investigation_harness.runner import (
    EvaluatedRunRequest,
    InvestigationEvent,
    InvestigatorExecution,
    InvestigatorExecutionFailure,
    InvestigatorUsage,
)


class InvestigationStage(StrEnum):
    PLANNING = "planning"
    EVIDENCE_GATHERING = "evidence-gathering"
    SYNTHESIS = "synthesis"
    COMPLETED = "completed"


class EvidenceQuery(BaseModel):
    """A read-only question for one authorized Evidence Provider."""

    model_config = ConfigDict(frozen=True)

    provider: AllowedEvidenceProvider
    question: str = Field(min_length=1, max_length=2_000)
    context: InvestigationContext | None = None


class EvidenceQueryResult(BaseModel):
    """Evidence and gaps returned by one provider query."""

    model_config = ConfigDict(frozen=True)

    provider: AllowedEvidenceProvider
    citations: tuple[EvidenceCitation, ...] = ()
    evidence: tuple[object, ...] = ()
    evidence_gaps: tuple[str, ...] = ()


class InvestigationPlan(BaseModel):
    """Initial bounded questions selected by the investigation strategy."""

    model_config = ConfigDict(frozen=True)

    initial_queries: tuple[EvidenceQuery, ...] = Field(min_length=1)


class ProviderFailure(RuntimeError):
    """A provider could not answer a read-only query."""


class SynthesisFailure(RuntimeError):
    """The collected evidence cannot produce a traceable report."""


class EvidenceQueryPort(Protocol):
    def __call__(self, query: EvidenceQuery) -> EvidenceQueryResult: ...


FollowUpSelector = Callable[[tuple[str, ...]], tuple[EvidenceQuery, ...]]
Synthesizer = Callable[[InvestigationContext, tuple[EvidenceQueryResult, ...]], InvestigationReport]


@dataclass(frozen=True)
class InvestigationStageResult:
    stage: InvestigationStage
    query_count: int
    detail: Mapping[str, object]


@dataclass(frozen=True)
class InvestigationCoordinatorResult:
    context: InvestigationContext
    stages: tuple[InvestigationStageResult, ...]
    results: tuple[EvidenceQueryResult, ...]
    citations: tuple[EvidenceCitation, ...]
    report: InvestigationReport | None
    stop_reason: str
    failure: str | None

    @property
    def events(self) -> tuple[InvestigationEvent, ...]:
        """Expose stage decisions as the same scoped audit events as the runner."""
        return tuple(
            InvestigationEvent(
                event_type=(
                    "investigation.failed"
                    if self.failure and stage.stage is InvestigationStage.COMPLETED
                    else f"investigation.{stage.stage.value}"
                ),
                incident_id=self.context.incident_id,
                investigation_run_id=self.context.investigation_run_id,
                payload={**stage.detail, "query_count": stage.query_count},
            )
            for stage in self.stages
        )


class InvestigationCoordinator:
    """Coordinate planning, bounded provider queries and report synthesis."""

    def __init__(
        self,
        query: EvidenceQueryPort,
        *,
        authorized_providers: tuple[AllowedEvidenceProvider, ...] = (
            "incident-mcp", "operations-mcp", "knowledge-mcp", "source-mcp"
        ),
        max_queries: int = 8,
        synthesize: Synthesizer | None = None,
    ) -> None:
        if max_queries < 1:
            raise ValueError("max_queries must be positive")
        self._query = query
        self._authorized = frozenset(authorized_providers)
        self._max_queries = max_queries
        self._synthesize = synthesize

    def run(
        self,
        context: InvestigationContext,
        *,
        plan: InvestigationPlan,
        follow_up: FollowUpSelector,
    ) -> InvestigationCoordinatorResult:
        stages: list[InvestigationStageResult] = [
            InvestigationStageResult(InvestigationStage.PLANNING, 0, {"queries": len(plan.initial_queries)})
        ]
        pending = plan.initial_queries
        gathered: list[EvidenceQueryResult] = []
        query_count = 0
        stop_reason = "sufficient-evidence"
        failure: str | None = None

        while pending:
            if query_count >= self._max_queries:
                stop_reason = "limit-exhausted"
                break
            query = pending[0]
            pending = pending[1:]
            if query.provider not in self._authorized:
                failure = f"Evidence Provider is not authorized: {query.provider}"
                stop_reason = "provider-failure"
                break
            scoped_query = query.model_copy(update={"context": context})
            try:
                result = self._query(scoped_query)
            except (ProviderFailure, ConnectionError, TimeoutError) as error:
                failure = str(error)
                stop_reason = "provider-failure"
                break
            if result.provider != query.provider:
                failure = (
                    f"Evidence Provider returned {result.provider} for {query.provider}"
                )
                stop_reason = "provider-failure"
                break
            if any(
                citation.incident_id != context.incident_id
                or citation.investigation_run_id != context.investigation_run_id
                for citation in result.citations
            ):
                failure = "Evidence Provider returned a citation from another Investigation Run"
                stop_reason = "provider-failure"
                break
            query_count += 1
            gathered.append(result)
            stages.append(InvestigationStageResult(
                InvestigationStage.EVIDENCE_GATHERING,
                query_count,
                {"provider": query.provider, "question": query.question},
            ))
            gaps = tuple(dict.fromkeys(result.evidence_gaps))
            if not gaps:
                break
            if query_count >= self._max_queries:
                stop_reason = "limit-exhausted"
                break
            pending = follow_up(gaps)
            if not pending:
                stop_reason = "calibrated-uncertainty"
                break

        if failure is None and query_count >= self._max_queries and pending:
            stop_reason = "limit-exhausted"
        if failure is None:
            report = None
            stages.append(InvestigationStageResult(
                InvestigationStage.SYNTHESIS, query_count, {"stop_reason": stop_reason}
            ))
            if self._synthesize is not None:
                try:
                    report = self._synthesize(context, tuple(gathered))
                    _validate_synthesized_report(report, context, gathered)
                except SynthesisFailure as error:
                    report = None
                    failure = str(error)
                    stop_reason = "synthesis-failure"
            stages.append(InvestigationStageResult(
                InvestigationStage.COMPLETED, query_count, {"reason": stop_reason}
            ))
        else:
            report = None
            stages.append(InvestigationStageResult(
                InvestigationStage.COMPLETED, query_count, {"reason": stop_reason, "error": failure}
            ))
        citations = tuple(citation for item in gathered for citation in item.citations)
        return InvestigationCoordinatorResult(
            context, tuple(stages), tuple(gathered), citations, report, stop_reason, failure
        )


Planner = Callable[[EvaluatedRunRequest, InvestigationEnvironment], InvestigationPlan]


class CoordinatorInvestigatorAdapter:
    """Adapt the coordinator to the runner's public InvestigatorAdapter port."""

    def __init__(
        self,
        planner: Planner,
        query: EvidenceQueryPort,
        follow_up: FollowUpSelector,
        synthesize: Synthesizer,
        *,
        max_queries: int = 8,
    ) -> None:
        self._planner = planner
        self._query = query
        self._follow_up = follow_up
        self._synthesize = synthesize
        self._max_queries = max_queries

    def investigate(
        self, request: EvaluatedRunRequest, environment: InvestigationEnvironment
    ) -> InvestigatorExecution:
        configured_limits = tuple(
            value for value in (request.limits.max_steps, request.limits.max_mcp_calls)
            if value is not None
        )
        if any(value == 0 for value in configured_limits):
            limit = "steps" if request.limits.max_steps == 0 else "mcp-calls"
            raise InvestigatorExecutionFailure(
                f"resource limit exhausted: {limit}", category="resource-limit",
                usage=InvestigatorUsage(), limit=limit,
            )
        coordinator = InvestigationCoordinator(
            self._query,
            authorized_providers=environment.allowed_evidence_providers,
            max_queries=min([
                self._max_queries,
                *(
                    value for value in (
                        request.limits.max_steps, request.limits.max_mcp_calls
                    ) if value is not None
                ),
            ]),
            synthesize=self._synthesize,
        )
        try:
            result = coordinator.run(
                request.context,
                plan=self._planner(request, environment),
                follow_up=self._follow_up,
            )
        except SynthesisFailure as error:
            raise InvestigatorExecutionFailure(
                str(error), category="invalid-output"
            ) from error
        if result.failure is not None:
            raise InvestigatorExecutionFailure(
                result.failure,
                result.events,
                category=(
                    "invalid-output"
                    if result.stop_reason == "synthesis-failure"
                    else "provider-unavailable"
                ),
            )
        usage = InvestigatorUsage(
            steps=sum(stage.stage is InvestigationStage.EVIDENCE_GATHERING for stage in result.stages),
            mcp_calls=len(result.results),
        )
        if result.stop_reason == "limit-exhausted":
            limit = "steps"
            if request.limits.max_mcp_calls is not None and (
                request.limits.max_steps is None
                or request.limits.max_mcp_calls < request.limits.max_steps
            ):
                limit = "mcp-calls"
            raise InvestigatorExecutionFailure(
                f"resource limit exhausted: {limit}", result.events,
                category="resource-limit", usage=usage, limit=limit,
            )
        if result.report is None:
            raise InvestigatorExecutionFailure(
                "coordinator produced no Investigation Report",
                result.events,
                category="report-missing",
            )
        return InvestigatorExecution(report=result.report, events=result.events, usage=usage)


def _validate_synthesized_report(
    report: InvestigationReport,
    context: InvestigationContext,
    gathered: list[EvidenceQueryResult],
) -> None:
    if report.incident_id != context.incident_id or report.investigation_run_id != context.investigation_run_id:
        raise SynthesisFailure("synthesized report belongs to another Investigation Run")
    gathered_citations = {
        citation for result in gathered for citation in result.citations
    }
    report_citations = {
        citation for claim in report.factual_claims for citation in claim.citations
    }
    if not gathered_citations.issubset(report_citations):
        raise SynthesisFailure("synthesized report omitted gathered evidence citations")
    if not report_citations.issubset(gathered_citations):
        raise SynthesisFailure("synthesized report introduced an unknown Evidence Citation")
