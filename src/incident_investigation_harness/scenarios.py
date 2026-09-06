from __future__ import annotations

import asyncio
from collections import Counter
from math import ceil
import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.adapters.notification_provider import (
    LocalNotificationProvider,
    ProviderFaultProfile,
)
from incident_investigation_harness.adapters.fakes import (
    NotificationQueueFake,
    NotificationRequestRepositoryFake,
)
from incident_investigation_harness.notifications import (
    NotificationMessage,
    NotificationRequestCreate,
    NotificationWorker,
)
from incident_investigation_harness.context import InvestigationContext


class ScenarioName(StrEnum):
    RETRY_STORM = "retry-storm"
    HEALTHY_REFERENCE = "healthy-reference"


class TrafficProfile(BaseModel):
    """Controlled traffic applied to one scenario execution."""

    model_config = ConfigDict(frozen=True)

    rounds: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    work_per_round: int = Field(ge=0)


class LatencyMeasurement(BaseModel):
    """Deterministic latency evidence for one operation and observation window."""

    model_config = ConfigDict(frozen=True)

    operation: str = Field(min_length=1)
    window: str = Field(min_length=1)
    samples: tuple[float, ...] = Field(min_length=1)
    p99: float = Field(ge=0)

    @property
    def sample_count(self) -> int:
        return len(self.samples)


class ScenarioComparison(BaseModel):
    """Comparison of reference and Retry Storm latency evidence."""

    model_config = ConfigDict(frozen=True)

    reference: OperationalSnapshot
    retry_storm: OperationalSnapshot
    degradation_threshold_percent: float = Field(gt=0)
    p99_degradation_percent: float
    is_degraded: bool


class OperationalSnapshot(BaseModel):
    """Read-only operational evidence for one completed scenario execution."""

    model_config = ConfigDict(frozen=True)

    scenario: ScenarioName
    execution_number: int = Field(gt=0)
    request_count: int = Field(ge=0)
    total_attempts: int = Field(ge=0)
    rate_limited_attempts: int = Field(ge=0)
    max_attempts_per_request: int = Field(ge=0)
    initial_backlog: int = Field(ge=0)
    final_backlog: int = Field(ge=0)
    peak_backlog: int = Field(ge=0)
    latency: LatencyMeasurement


class _Scenario:
    name: ScenarioName
    rate_limit_attempts: int
    traffic_profile: TrafficProfile

    def __init__(self) -> None:
        self.execution_number = 0
        self._snapshot: OperationalSnapshot | None = None

    @property
    def snapshot(self) -> OperationalSnapshot | None:
        """Return the latest execution snapshot, if one has completed."""
        return self._snapshot

    def reset(self) -> None:
        """Discard the previous snapshot and start the next run cleanly."""
        self._snapshot = None

    def run(self) -> OperationalSnapshot:
        self.reset()
        self.execution_number += 1
        self._snapshot = asyncio.run(self._run())
        return self._snapshot

    async def _run(self) -> OperationalSnapshot:
        request_repository = NotificationRequestRepositoryFake()
        queue = NotificationQueueFake()
        provider = LocalNotificationProvider()
        provider.configure_fault_profile(
            ProviderFaultProfile(rate_limit_attempts=self.rate_limit_attempts)
        )
        worker = NotificationWorker(
            request_repository,
            queue,
            provider,
            retry_rate_limited=self.rate_limit_attempts > 0,
        )
        attempts_by_request: Counter[str] = Counter()
        latency_samples: list[float] = []
        peak_backlog = queue.depth()

        for _ in range(self.traffic_profile.rounds):
            for _ in range(self.traffic_profile.batch_size):
                request_index = len(request_repository.requests)
                request = request_repository.create(
                    NotificationRequestCreate(
                        # The scenario exercises notification operations directly;
                        # ticket persistence remains owned by PostgreSQL.
                        ticket_id=uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            f"{self.name}-{self.execution_number}-{request_index}",
                        ),
                        recipient_email="oncall@example.com",
                        investigation_context=InvestigationContext(
                            incident_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"incident-{self.name}"),
                            investigation_run_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"run-{self.name}-{self.execution_number}"),
                        ),
                    )
                )
                queue.publish(
                    NotificationMessage(
                        request_id=request.id,
                        ticket_id=request.ticket_id,
                        investigation_context=request.investigation_context,
                    )
                )
            peak_backlog = max(peak_backlog, queue.depth())

            for _ in range(self.traffic_profile.work_per_round):
                message = queue.pop()
                if message is None:
                    break
                attempts_by_request[str(message.request_id)] += 1
                await worker.process(message)
                # The harness measures processing latency in deterministic
                # work units, including the backlog left by the operation.
                latency_samples.append(float(1 + queue.depth()))
                peak_backlog = max(peak_backlog, queue.depth())

        rate_limited_attempts = sum(
            attempt.status_code == 429 for attempt in provider.attempts
        )
        return OperationalSnapshot(
            scenario=self.name,
            execution_number=self.execution_number,
            request_count=len(request_repository.requests),
            total_attempts=len(provider.attempts),
            rate_limited_attempts=rate_limited_attempts,
            max_attempts_per_request=max(attempts_by_request.values(), default=0),
            initial_backlog=0,
            final_backlog=queue.depth(),
            peak_backlog=peak_backlog,
            latency=LatencyMeasurement(
                operation="notification-processing",
                window=f"{self.traffic_profile.rounds} traffic rounds",
                samples=tuple(latency_samples),
                p99=_percentile(latency_samples, 0.99),
            ),
        )


class RetryStormScenario(_Scenario):
    """Deterministic scenario with unbounded immediate retries after 429."""

    name = ScenarioName.RETRY_STORM
    traffic_profile = TrafficProfile(rounds=8, batch_size=2, work_per_round=1)
    rate_limit_attempts = 1000


class HealthyScenario(_Scenario):
    """Deterministic no-fault reference scenario with enough worker capacity."""

    name = ScenarioName.HEALTHY_REFERENCE
    traffic_profile = TrafficProfile(rounds=8, batch_size=2, work_per_round=2)
    rate_limit_attempts = 0


def _percentile(samples: list[float], percentile: float) -> float:
    ordered_samples = sorted(samples)
    rank = max(1, ceil(percentile * len(ordered_samples)))
    return ordered_samples[rank - 1]


def compare_scenarios(
    reference: OperationalSnapshot,
    retry_storm: OperationalSnapshot,
    *,
    degradation_threshold_percent: float = 25.0,
) -> ScenarioComparison:
    """Compare p99 latency without requiring equal execution durations."""
    reference_p99 = reference.latency.p99
    p99_degradation_percent = (
        (retry_storm.latency.p99 - reference_p99) / reference_p99 * 100
        if reference_p99
        else 0.0
    )
    return ScenarioComparison(
        reference=reference,
        retry_storm=retry_storm,
        degradation_threshold_percent=degradation_threshold_percent,
        p99_degradation_percent=p99_degradation_percent,
        is_degraded=p99_degradation_percent >= degradation_threshold_percent,
    )
