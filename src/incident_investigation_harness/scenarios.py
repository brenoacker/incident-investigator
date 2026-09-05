from __future__ import annotations

import asyncio
from collections import Counter
import uuid

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.adapters.notification_provider import (
    LocalNotificationProvider,
    ProviderFaultProfile,
)
from incident_investigation_harness.adapters.in_memory import (
    InMemoryNotificationQueue,
    InMemoryNotificationRequestRepository,
)
from incident_investigation_harness.notifications import (
    NotificationMessage,
    NotificationRequestCreate,
    NotificationWorker,
)


class OperationalSnapshot(BaseModel):
    """Read-only operational evidence for one completed scenario execution."""

    model_config = ConfigDict(frozen=True)

    scenario: str
    execution_number: int = Field(gt=0)
    request_count: int = Field(ge=0)
    total_attempts: int = Field(ge=0)
    rate_limited_attempts: int = Field(ge=0)
    max_attempts_per_request: int = Field(ge=0)
    initial_backlog: int = Field(ge=0)
    final_backlog: int = Field(ge=0)
    peak_backlog: int = Field(ge=0)


class _Scenario:
    name: str
    traffic_batch_size: int
    work_per_round: int
    rate_limit_attempts: int
    rounds: int = 8

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
        request_repository = InMemoryNotificationRequestRepository()
        queue = InMemoryNotificationQueue()
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
        peak_backlog = queue.depth()

        for _ in range(self.rounds):
            for _ in range(self.traffic_batch_size):
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
                    )
                )
                queue.publish(
                    NotificationMessage(
                        request_id=request.id, ticket_id=request.ticket_id
                    )
                )
            peak_backlog = max(peak_backlog, queue.depth())

            for _ in range(self.work_per_round):
                message = queue.pop()
                if message is None:
                    break
                attempts_by_request[str(message.request_id)] += 1
                await worker.process(message)
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
        )


class RetryStormScenario(_Scenario):
    """Deterministic scenario with unbounded immediate retries after 429."""

    name = "retry-storm"
    traffic_batch_size = 2
    work_per_round = 1
    rate_limit_attempts = 1000


class HealthyScenario(_Scenario):
    """Deterministic no-fault reference scenario with enough worker capacity."""

    name = "healthy-reference"
    traffic_batch_size = 2
    work_per_round = 2
    rate_limit_attempts = 0
