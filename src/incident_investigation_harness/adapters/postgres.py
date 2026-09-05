from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import psycopg

from incident_investigation_harness.notifications import (
    NotificationRequest,
    NotificationRequestCreate,
)
from incident_investigation_harness.tickets import Ticket, TicketCreate


class PostgresTicketRepository:
    """PostgreSQL adapter for the TicketRepository port."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def initialize(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id UUID PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL,
                    requester_email VARCHAR(320) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )

    def create(self, ticket: TicketCreate) -> Ticket:
        created = Ticket(
            id=uuid.uuid4(),
            title=ticket.title,
            description=ticket.description,
            requester_email=ticket.requester_email,
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                INSERT INTO tickets
                    (id, title, description, requester_email, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    created.id,
                    created.title,
                    created.description,
                    created.requester_email,
                    created.status,
                    created.created_at,
                ),
            )
        return created

    def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT id, title, description, requester_email, status, created_at
                FROM tickets
                WHERE id = %s
                """,
                (ticket_id,),
            ).fetchone()
        if row is None:
            return None
        return Ticket(
            id=row[0],
            title=row[1],
            description=row[2],
            requester_email=row[3],
            status=row[4],
            created_at=row[5],
        )


class PostgresNotificationRequestRepository:
    """PostgreSQL adapter for persisted notification requests."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def initialize(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_requests (
                    id UUID PRIMARY KEY,
                    ticket_id UUID NOT NULL REFERENCES tickets(id),
                    recipient_email VARCHAR(320) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )

    def create(self, request: NotificationRequestCreate) -> NotificationRequest:
        created = NotificationRequest(
            id=uuid.uuid4(),
            ticket_id=request.ticket_id,
            recipient_email=request.recipient_email,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                INSERT INTO notification_requests
                    (id, ticket_id, recipient_email, status, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    created.id,
                    created.ticket_id,
                    created.recipient_email,
                    created.status,
                    created.created_at,
                ),
            )
        return created

    def get(self, request_id: uuid.UUID) -> NotificationRequest | None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT id, ticket_id, recipient_email, status, created_at
                FROM notification_requests
                WHERE id = %s
                """,
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return NotificationRequest(
            id=row[0],
            ticket_id=row[1],
            recipient_email=row[2],
            status=row[3],
            created_at=row[4],
        )


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://ticketing:ticketing@db:5432/ticketing",
    )
