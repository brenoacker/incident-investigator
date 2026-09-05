from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from incident_investigation_harness.context import InvestigationContext


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    requester_email: EmailStr
    investigation_context: InvestigationContext


class Ticket(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    requester_email: EmailStr
    status: str
    created_at: datetime
    investigation_context: InvestigationContext


class TicketRepository(Protocol):
    def create(self, ticket: TicketCreate) -> Ticket: ...

    def get(self, ticket_id: uuid.UUID) -> Ticket | None: ...

    def list_by_investigation_run_id(
        self, investigation_run_id: uuid.UUID
    ) -> list[Ticket]: ...


class TicketNotFound(Exception):
    """Raised when a requested ticket does not exist."""


def create_ticket(repository: TicketRepository, ticket: TicketCreate) -> Ticket:
    return repository.create(ticket)


def find_ticket(repository: TicketRepository, ticket_id: uuid.UUID) -> Ticket:
    ticket = repository.get(ticket_id)
    if ticket is None:
        raise TicketNotFound(ticket_id)
    return ticket
