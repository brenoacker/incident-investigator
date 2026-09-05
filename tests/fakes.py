from __future__ import annotations

import uuid
from datetime import datetime, timezone

from incident_investigation_harness.adapters.in_memory import (
    InMemoryNotificationQueue,
    InMemoryNotificationRequestRepository,
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
