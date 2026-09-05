from __future__ import annotations

import uuid
from datetime import datetime
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


class NotificationMessage(BaseModel):
    request_id: uuid.UUID
    ticket_id: uuid.UUID


class NotificationRequestRepository(Protocol):
    def create(self, request: NotificationRequestCreate) -> NotificationRequest: ...

    def get(self, request_id: uuid.UUID) -> NotificationRequest | None: ...


class NotificationQueue(Protocol):
    def publish(self, message: NotificationMessage) -> None: ...

    def pop(self) -> NotificationMessage | None: ...


class NotificationRequestNotFound(Exception):
    """Raised when a requested notification request does not exist."""


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
