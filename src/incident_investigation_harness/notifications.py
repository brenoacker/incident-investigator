from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, ConfigDict, EmailStr

from incident_investigation_harness.tickets import TicketRepository, find_ticket


class NotificationRequestCreate(BaseModel):
    ticket_id: uuid.UUID
    recipient_email: EmailStr


class NotificationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    recipient_email: EmailStr
    status: str
    created_at: datetime
    delivery_result: str | None = None
    delivered_at: datetime | None = None


class NotificationMessage(BaseModel):
    request_id: uuid.UUID
    ticket_id: uuid.UUID


class NotificationRequestRepository(Protocol):
    def create(self, request: NotificationRequestCreate) -> NotificationRequest: ...

    def get(self, request_id: uuid.UUID) -> NotificationRequest | None: ...

    def mark_delivered(
        self, request_id: uuid.UUID, result: str, delivered_at: datetime
    ) -> NotificationRequest: ...


class NotificationDelivery(BaseModel):
    result: str


class NotificationProvider(Protocol):
    def deliver(self, recipient_email: str) -> NotificationDelivery: ...


class NotificationQueue(Protocol):
    def publish(self, message: NotificationMessage) -> None: ...

    def pop(self) -> NotificationMessage | None: ...


class NotificationRequestNotFound(Exception):
    """Raised when a requested notification request does not exist."""


class NotificationWorker:
    def __init__(
        self,
        request_repository: NotificationRequestRepository,
        queue: NotificationQueue,
        provider: NotificationProvider,
    ) -> None:
        self.request_repository = request_repository
        self.queue = queue
        self.provider = provider

    async def process_next(self) -> bool:
        message = self.queue.pop()
        if message is None:
            return False
        await self.process(message)
        return True

    async def process(self, message: NotificationMessage) -> None:
        request = self.request_repository.get(message.request_id)
        if request is None or request.status == "delivered":
            return

        delivery = self.provider.deliver(request.recipient_email)
        self.request_repository.mark_delivered(
            request.id,
            delivery.result,
            datetime.now(timezone.utc),
        )


def request_notification(
    ticket_repository: TicketRepository,
    request_repository: NotificationRequestRepository,
    queue: NotificationQueue,
    ticket_id: uuid.UUID,
) -> NotificationRequest:
    ticket = find_ticket(ticket_repository, ticket_id)
    request = request_repository.create(
        NotificationRequestCreate(
            ticket_id=ticket.id,
            recipient_email=ticket.requester_email,
        )
    )
    queue.publish(
        NotificationMessage(request_id=request.id, ticket_id=request.ticket_id)
    )
    return request


def find_notification_request(
    repository: NotificationRequestRepository,
    request_id: uuid.UUID,
) -> NotificationRequest:
    request = repository.get(request_id)
    if request is None:
        raise NotificationRequestNotFound(request_id)
    return request
