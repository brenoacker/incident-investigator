from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.notifications import NotificationDeliveryResult, NotificationRequest, NotificationRequestCreate, NotificationStatus
from incident_investigation_harness.tickets import Ticket, TicketCreate


def _ticket(row: tuple[Any, ...]) -> Ticket:
    return Ticket(id=row[0], title=row[1], description=row[2], requester_email=row[3], status=row[4], created_at=row[5], investigation_context=InvestigationContext(incident_id=row[6], investigation_run_id=row[7]))


def _request(row: tuple[Any, ...]) -> NotificationRequest:
    return NotificationRequest(id=row[0], ticket_id=row[1], recipient_email=row[2], status=NotificationStatus(row[3]), created_at=row[4], delivery_result=NotificationDeliveryResult(row[5]) if row[5] else None, delivered_at=row[6], investigation_context=InvestigationContext(incident_id=row[7], investigation_run_id=row[8]))


class PostgresTicketRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def initialize(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS tickets (id UUID PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT NOT NULL, requester_email VARCHAR(320) NOT NULL, status VARCHAR(32) NOT NULL, created_at TIMESTAMPTZ NOT NULL, incident_id UUID NOT NULL, investigation_run_id UUID NOT NULL)""")
            connection.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS incident_id UUID, ADD COLUMN IF NOT EXISTS investigation_run_id UUID")

    def create(self, ticket: TicketCreate) -> Ticket:
        created = Ticket(id=uuid.uuid4(), title=ticket.title, description=ticket.description, requester_email=ticket.requester_email, status="open", created_at=datetime.now(timezone.utc), investigation_context=ticket.investigation_context)
        with psycopg.connect(self.database_url) as connection:
            connection.execute("INSERT INTO tickets (id, title, description, requester_email, status, created_at, incident_id, investigation_run_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (created.id, created.title, created.description, created.requester_email, created.status, created.created_at, created.investigation_context.incident_id, created.investigation_context.investigation_run_id))
        return created

    def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute("SELECT id, title, description, requester_email, status, created_at, incident_id, investigation_run_id FROM tickets WHERE id = %s", (ticket_id,)).fetchone()
        return _ticket(row) if row else None

    def list_by_investigation_run_id(self, investigation_run_id: uuid.UUID) -> list[Ticket]:
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute("SELECT id, title, description, requester_email, status, created_at, incident_id, investigation_run_id FROM tickets WHERE investigation_run_id = %s ORDER BY created_at, id", (investigation_run_id,)).fetchall()
        return [_ticket(row) for row in rows]


class PostgresNotificationRequestRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def initialize(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS notification_requests (id UUID PRIMARY KEY, ticket_id UUID NOT NULL REFERENCES tickets(id), recipient_email VARCHAR(320) NOT NULL, status VARCHAR(32) NOT NULL, created_at TIMESTAMPTZ NOT NULL, delivery_result VARCHAR(64), delivered_at TIMESTAMPTZ, incident_id UUID NOT NULL, investigation_run_id UUID NOT NULL)""")
            connection.execute("ALTER TABLE notification_requests ADD COLUMN IF NOT EXISTS delivery_result VARCHAR(64), ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ, ADD COLUMN IF NOT EXISTS incident_id UUID, ADD COLUMN IF NOT EXISTS investigation_run_id UUID")

    def create(self, request: NotificationRequestCreate) -> NotificationRequest:
        created = NotificationRequest(id=uuid.uuid4(), ticket_id=request.ticket_id, recipient_email=request.recipient_email, status=NotificationStatus.PENDING, created_at=datetime.now(timezone.utc), investigation_context=request.investigation_context)
        with psycopg.connect(self.database_url) as connection:
            connection.execute("INSERT INTO notification_requests (id, ticket_id, recipient_email, status, created_at, incident_id, investigation_run_id) VALUES (%s, %s, %s, %s, %s, %s, %s)", (created.id, created.ticket_id, created.recipient_email, created.status, created.created_at, created.investigation_context.incident_id, created.investigation_context.investigation_run_id))
        return created

    def get(self, request_id: uuid.UUID) -> NotificationRequest | None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute("SELECT id, ticket_id, recipient_email, status, created_at, delivery_result, delivered_at, incident_id, investigation_run_id FROM notification_requests WHERE id = %s", (request_id,)).fetchone()
        return _request(row) if row else None

    def list_by_investigation_run_id(self, investigation_run_id: uuid.UUID) -> list[NotificationRequest]:
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute("SELECT id, ticket_id, recipient_email, status, created_at, delivery_result, delivered_at, incident_id, investigation_run_id FROM notification_requests WHERE investigation_run_id = %s ORDER BY created_at, id", (investigation_run_id,)).fetchall()
        return [_request(row) for row in rows]

    def mark_delivered(self, request_id: uuid.UUID, result: NotificationDeliveryResult, delivered_at: datetime) -> NotificationRequest:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute("UPDATE notification_requests SET status = %s, delivery_result = %s, delivered_at = %s WHERE id = %s RETURNING id, ticket_id, recipient_email, status, created_at, delivery_result, delivered_at, incident_id, investigation_run_id", (NotificationStatus.DELIVERED, result, delivered_at, request_id)).fetchone()
        if row is None:
            raise ValueError(f"notification request {request_id} not found")
        return _request(row)


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://ticketing:ticketing@db:5432/ticketing")
