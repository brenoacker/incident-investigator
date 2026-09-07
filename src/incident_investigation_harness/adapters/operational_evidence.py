from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, overload

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.operational_evidence import (
    CitedOperationalLog,
    CitedOperationalMetric,
    CitedOperationalTrace,
    OperationalEvidenceQuery,
    OperationalEvidenceResponse,
    OperationalLog,
    OperationalMetric,
    OperationalTrace,
)


@dataclass(frozen=True)
class OperationalEvidenceRepositoryFake:
    logs: tuple[OperationalLog, ...]
    metrics: tuple[OperationalMetric, ...]
    traces: tuple[OperationalTrace, ...]

    def query(self, query: OperationalEvidenceQuery) -> OperationalEvidenceResponse:
        allowed = query.evidence_types
        logs = tuple(
            self._cite(item, "operational-log")
            for item in self.logs
            if self._matches(item.investigation_context, query)
            and (allowed is None or "operational-log" in allowed)
        )
        metrics = tuple(
            self._cite(item, "operational-metric")
            for item in self.metrics
            if self._matches(item.investigation_context, query)
            and (allowed is None or "operational-metric" in allowed)
            and (query.operation is None or item.operation == query.operation)
        )
        traces = tuple(
            self._cite(item, "operational-trace")
            for item in self.traces
            if self._matches(item.investigation_context, query)
            and (allowed is None or "operational-trace" in allowed)
            and (query.operation is None or item.operation == query.operation)
        )
        return OperationalEvidenceResponse(
            context=query.context, logs=logs, metrics=metrics, traces=traces
        )

    def resolve(
        self, citation: EvidenceCitation
    ) -> CitedOperationalLog | CitedOperationalMetric | CitedOperationalTrace | None:
        if citation.provider != "operations-mcp":
            raise ValueError("citation provider must be operations-mcp")
        context = InvestigationContext(
            incident_id=citation.incident_id,
            investigation_run_id=citation.investigation_run_id,
        )
        if citation.evidence_type == "operational-log":
            for item in self.logs:
                if item.id == citation.evidence_id and item.investigation_context == context:
                    return self._cite(item, "operational-log")
        elif citation.evidence_type == "operational-metric":
            for metric in self.metrics:
                if metric.id == citation.evidence_id and metric.investigation_context == context:
                    return self._cite(metric, "operational-metric")
        elif citation.evidence_type == "operational-trace":
            for trace in self.traces:
                if trace.id == citation.evidence_id and trace.investigation_context == context:
                    return self._cite(trace, "operational-trace")
        return None

    @staticmethod
    def _matches(
        item_context: InvestigationContext, query: OperationalEvidenceQuery
    ) -> bool:
        return item_context == query.context

    @staticmethod
    @overload
    def _cite(item: OperationalLog, evidence_type: Literal["operational-log"]) -> CitedOperationalLog: ...

    @staticmethod
    @overload
    def _cite(item: OperationalMetric, evidence_type: Literal["operational-metric"]) -> CitedOperationalMetric: ...

    @staticmethod
    @overload
    def _cite(item: OperationalTrace, evidence_type: Literal["operational-trace"]) -> CitedOperationalTrace: ...

    @staticmethod
    def _cite(
        item: OperationalLog | OperationalMetric | OperationalTrace,
        evidence_type: Literal[
            "operational-log", "operational-metric", "operational-trace"
        ],
    ) -> CitedOperationalLog | CitedOperationalMetric | CitedOperationalTrace:
        context = item.investigation_context
        citation = EvidenceCitation(
            provider="operations-mcp",
            incident_id=context.incident_id,
            investigation_run_id=context.investigation_run_id,
            evidence_type=evidence_type,
            evidence_id=item.id,
        )
        if evidence_type == "operational-log":
            assert isinstance(item, OperationalLog)
            return CitedOperationalLog(item=item, citation=citation)
        if evidence_type == "operational-metric":
            assert isinstance(item, OperationalMetric)
            return CitedOperationalMetric(item=item, citation=citation)
        assert isinstance(item, OperationalTrace)
        return CitedOperationalTrace(item=item, citation=citation)


def build_operational_evidence_repository() -> OperationalEvidenceRepositoryFake:
    context = _context("retry-storm", 1)
    other_context = _context("healthy-reference", 1)
    timestamp = datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)
    logs = [
            OperationalLog(
                id=_id("log-retry-storm-429"),
                investigation_context=context,
                timestamp=timestamp,
                level="WARN",
                message="notification-provider returned 429",
                values={"status_code": 429, "attempts": 16},
            ),
            OperationalLog(
                id=_id("log-healthy"),
                investigation_context=other_context,
                timestamp=timestamp,
                level="INFO",
                message="notification processing completed",
                values={"status_code": 202, "attempts": 1},
            ),
    ]
    metrics = [
            OperationalMetric(
                id=_id("metric-retry-storm-attempts"),
                investigation_context=context,
                timestamp=timestamp,
                name="notification.attempts.total",
                value=16,
                unit="attempts",
                operation="notification-processing",
            ),
            OperationalMetric(
                id=_id("metric-retry-storm-backlog"),
                investigation_context=context,
                timestamp=timestamp,
                name="notification.backlog",
                value=8,
                unit="messages",
                operation="notification-processing",
            ),
            OperationalMetric(
                id=_id("metric-retry-storm-p99"),
                investigation_context=context,
                timestamp=timestamp,
                name="notification.latency.p99",
                value=16,
                unit="work-units",
                operation="notification-processing",
            ),
    ]
    traces = [
            OperationalTrace(
                id=_id("trace-retry-storm"),
                investigation_context=context,
                timestamp=timestamp,
                operation="notification-processing",
                duration_ms=16,
                status_code=429,
                values={"attempts": 16, "backlog": 8, "p99": 16},
            ),
    ]
    for scenario in ("retry-storm", "ambiguous-evidence", "prompt-injection"):
        for execution_number in range(2, 11):
            run_context = _context(scenario, execution_number)
            logs.append(
                OperationalLog(
                    id=_id(f"log-{scenario}-429-{execution_number}"),
                    investigation_context=run_context,
                    timestamp=timestamp,
                    level="WARN",
                    message="notification-provider returned 429; queue latency increased",
                    values={"status_code": 429, "attempts": 16},
                )
            )
            metrics.extend(
                (
                    OperationalMetric(
                        id=_id(f"metric-{scenario}-attempts-{execution_number}"),
                        investigation_context=run_context,
                        timestamp=timestamp,
                        name="notification.attempts.total",
                        value=16,
                        unit="attempts",
                        operation="notification-processing",
                    ),
                    OperationalMetric(
                        id=_id(f"metric-{scenario}-backlog-{execution_number}"),
                        investigation_context=run_context,
                        timestamp=timestamp,
                        name="notification.backlog",
                        value=8,
                        unit="messages",
                        operation="notification-processing",
                    ),
                    OperationalMetric(
                        id=_id(f"metric-{scenario}-p99-{execution_number}"),
                        investigation_context=run_context,
                        timestamp=timestamp,
                        name="notification.latency.p99",
                        value=16,
                        unit="work-units",
                        operation="notification-processing",
                    ),
                )
            )
            traces.append(
                OperationalTrace(
                    id=_id(f"trace-{scenario}-{execution_number}"),
                    investigation_context=run_context,
                    timestamp=timestamp,
                    operation="notification-processing",
                    duration_ms=16,
                    status_code=429,
                    values={"attempts": 16, "backlog": 8, "p99": 16},
                )
            )
    ambiguous_context = _context("ambiguous-evidence", 1)
    logs.append(
        OperationalLog(
            id=_id("log-ambiguous-evidence-429"),
            investigation_context=ambiguous_context,
            timestamp=timestamp,
            level="WARN",
            message="notification-provider returned 429",
            values={"status_code": 429},
        )
    )
    return OperationalEvidenceRepositoryFake(
        logs=tuple(logs), metrics=tuple(metrics), traces=tuple(traces)
    )


def _context(scenario: str, execution_number: int) -> InvestigationContext:
    return InvestigationContext(
        incident_id=_id(f"incident-{scenario}"),
        investigation_run_id=_id(f"run-{scenario}-{execution_number}"),
    )


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:{value}")
