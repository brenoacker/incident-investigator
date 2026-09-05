from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import httpx

from incident_investigation_harness.app import app
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


def test_ticket_api_creates_and_reads_a_ticket() -> None:
    repository = InMemoryTicketRepository()
    app.state.ticket_repository = repository

    created, fetched = asyncio.run(_create_and_fetch_ticket())

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    assert created.json()["title"] == "Notification delivery is delayed"
    assert created.json()["description"] == "The incident timeline shows increasing delivery latency."


def test_ticket_api_rejects_invalid_data_without_creating_a_ticket() -> None:
    repository = InMemoryTicketRepository()
    app.state.ticket_repository = repository

    response = asyncio.run(_create_invalid_ticket())

    assert response.status_code == 422
    assert repository.tickets == {}


async def _create_and_fetch_ticket() -> tuple[httpx.Response, httpx.Response]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/tickets",
            json={
                "title": "  Notification delivery is delayed  ",
                "description": "  The incident timeline shows increasing delivery latency.  ",
                "requester_email": "oncall@example.com",
            },
        )
        fetched = await client.get(f"/tickets/{created.json()['id']}")
        return created, fetched


async def _create_invalid_ticket() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/tickets",
            json={
                "title": "",
                "description": "",
                "requester_email": "oncall@example.com",
                "unexpected": "must be rejected",
            },
        )
