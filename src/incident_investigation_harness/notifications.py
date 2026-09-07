from __future__ import annotations

import asyncio
from time import perf_counter
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, EmailStr

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.tickets import TicketRepository, find_ticket
from incident_investigation_harness.telemetry import span, telemetry


class NotificationStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"


class NotificationDeliveryResult(StrEnum):
    ACCEPTED = "accepted"
    RATE_LIMITED = "rate_limited"


class NotificationRequestCreate(BaseModel):
    ticket_id: uuid.UUID
    recipient_email: EmailStr
    investigation_context: InvestigationContext


class NotificationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    recipient_email: EmailStr
    status: NotificationStatus
    created_at: datetime
    delivery_result: NotificationDeliveryResult | None = None
    delivered_at: datetime | None = None
    investigation_context: InvestigationContext


class NotificationMessage(BaseModel):
    request_id: uuid.UUID
    ticket_id: uuid.UUID
    investigation_context: InvestigationContext


class NotificationRequestRepository(Protocol):
    def create(self, request: NotificationRequestCreate) -> NotificationRequest: ...

    def get(self, request_id: uuid.UUID) -> NotificationRequest | None: ...

    def list_by_investigation_run_id(
        self, investigation_run_id: uuid.UUID
    ) -> list[NotificationRequest]: ...

    def mark_delivered(
        self,
        request_id: uuid.UUID,
        result: NotificationDeliveryResult,
        delivered_at: datetime,
    ) -> NotificationRequest: ...


class NotificationDelivery(BaseModel):
    result: NotificationDeliveryResult
    status_code: int = 202


class NotificationProvider(Protocol):
    def deliver(
        self,
        recipient_email: str,
        investigation_context: InvestigationContext,
    ) -> NotificationDelivery: ...


class NotificationQueue(Protocol):
    def publish(self, message: NotificationMessage) -> None: ...

    def pop(self) -> NotificationMessage | None: ...

    def depth(self) -> int: ...


class NotificationRequestNotFound(Exception):
    """Raised when a requested notification request does not exist."""


class NotificationWorker:
    def __init__(
        self,
        request_repository: NotificationRequestRepository,
        queue: NotificationQueue,
        provider: NotificationProvider,
        retry_rate_limited: bool = False,
    ) -> None:
        self.request_repository = request_repository
        self.queue = queue
        self.provider = provider
        self.retry_rate_limited = retry_rate_limited

    async def process_next(self) -> bool:
        message = self.queue.pop()
        if message is None:
            return False
        telemetry.notification_backlog.add(-1)
        await self.process(message)
        return True

    async def run_forever(
        self,
        poll_interval: float = 0.1,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        while stop_event is None or not stop_event.is_set():
            processed = await self.process_next()
            if not processed:
                await asyncio.sleep(poll_interval)

    async def process(self, message: NotificationMessage) -> None:
        started = perf_counter()
        try:
            await self._process(message)
        finally:
            telemetry.notification_duration.record(perf_counter() - started)

    async def _process(self, message: NotificationMessage) -> None:
        with span(
            "notification.process",
            context=message.investigation_context,
            component="notification-worker",
            operation="process",
        ):
            telemetry.notification_attempts.add(1)
            request = self.request_repository.get(message.request_id)
            if request is None or request.status == NotificationStatus.DELIVERED:
                return

            delivery = self.provider.deliver(
                request.recipient_email, request.investigation_context
            )
            if delivery.result == NotificationDeliveryResult.RATE_LIMITED:
                telemetry.notifications.add(1, {"result": "rate_limited"})
                if self.retry_rate_limited:
                    self.queue.publish(message)
                    telemetry.notification_retries.add(1)
                return
            self.request_repository.mark_delivered(
                request.id,
                delivery.result,
                datetime.now(timezone.utc),
            )
            telemetry.notifications.add(1, {"result": "accepted"})


def request_notification(
    ticket_repository: TicketRepository,
    request_repository: NotificationRequestRepository,
    queue: NotificationQueue,
    ticket_id: uuid.UUID,
) -> NotificationRequest:
    with span(
        "notification.request",
        component="ticketing-saas",
        operation="request-notification",
    ):
        ticket = find_ticket(ticket_repository, ticket_id)
        request = request_repository.create(
            NotificationRequestCreate(
                ticket_id=ticket.id,
                recipient_email=ticket.requester_email,
                investigation_context=ticket.investigation_context,
            )
        )
        queue.publish(
            NotificationMessage(
                request_id=request.id,
                ticket_id=request.ticket_id,
                investigation_context=request.investigation_context,
            )
        )
        telemetry.notification_backlog.add(1)
        return request


def find_notification_request(
    repository: NotificationRequestRepository,
    request_id: uuid.UUID,
) -> NotificationRequest:
    request = repository.get(request_id)
    if request is None:
        raise NotificationRequestNotFound(request_id)
    return request
