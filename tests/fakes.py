from __future__ import annotations

import uuid
from datetime import datetime, timezone

from incident_investigation_harness.notifications import (
    NotificationMessage,
    NotificationRequest,
    NotificationRequestCreate,
)
from incident_investigation_harness.tickets import Ticket, TicketCreate


class InMemoryTicketRepository:
    def __init__(self) -> None:
        self.tickets: dict[uuid.UUID, Ticket] = {}

    def create(self, ticket: TicketCreate) -> Ticket:
        created = Ticket(
            id=uuid.uuid4(),
            title=ticket.title,
            description=ticket.description,
            requester_email=ticket.requester_email,
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        self.tickets[created.id] = created
        return created

    def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        return self.tickets.get(ticket_id)


class InMemoryNotificationRequestRepository:
    def __init__(self) -> None:
        self.requests: dict[uuid.UUID, NotificationRequest] = {}

    def create(self, request: NotificationRequestCreate) -> NotificationRequest:
        created = NotificationRequest(
            id=uuid.uuid4(),
            ticket_id=request.ticket_id,
            recipient_email=request.recipient_email,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        self.requests[created.id] = created
        return created

    def get(self, request_id: uuid.UUID) -> NotificationRequest | None:
        return self.requests.get(request_id)


class InMemoryNotificationQueue:
    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def publish(self, message: NotificationMessage) -> None:
        self.messages.append(message)

    def pop(self) -> NotificationMessage | None:
        return self.messages.pop(0) if self.messages else None
