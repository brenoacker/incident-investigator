from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from incident_investigation_harness.adapters.incident_evidence import (
    IncidentEvidenceRepositoryFake,
)
from incident_investigation_harness.adapters.knowledge_evidence import (
    KnowledgeEvidenceAdapter,
)
from incident_investigation_harness.adapters.source_evidence import SourceEvidenceAdapter
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import TimelineEvent, TicketComment
from incident_investigation_harness.tickets import Ticket


def build_incident_evidence_repository() -> IncidentEvidenceRepositoryFake:
    """Build deterministic evidence for local MCP development and evaluation."""
    first_context = _context("retry-storm", 1)
    second_context = _context("healthy-reference", 1)
    first_ticket = _ticket(first_context, "Notification delivery degraded")
    second_ticket = _ticket(second_context, "Notification delivery healthy")

    return IncidentEvidenceRepositoryFake(
        tickets=[first_ticket, second_ticket],
        comments=[
            TicketComment(
                id=_id("comment-retry-storm"),
                ticket_id=first_ticket.id,
                investigation_context=first_context,
                author="oncall@example.com",
                body="The provider returned 429 and the backlog increased.",
                created_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
            ),
            TicketComment(
                id=_id("comment-healthy-reference"),
                ticket_id=second_ticket.id,
                investigation_context=second_context,
                author="oncall@example.com",
                body="The reference execution completed without rate limits.",
                created_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
            ),
        ],
        timeline=[
            TimelineEvent(
                id=_id("event-retry-storm-started"),
                investigation_context=first_context,
                event_type="observation",
                description="Notification latency started increasing.",
                occurred_at=datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
            ),
            TimelineEvent(
                id=_id("event-healthy-reference-completed"),
                investigation_context=second_context,
                event_type="observation",
                description="The healthy reference completed within expected latency.",
                occurred_at=datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
            ),
        ],
    )


def build_knowledge_evidence_repository() -> KnowledgeEvidenceAdapter:
    """Build the explicit read-only knowledge allowlist for local MCP use."""
    return KnowledgeEvidenceAdapter.from_allowlist(
        Path("."),
        frozenset(
            {
                "docs/scenarios/retry-storm-latency.md",
                "docs/adr/0001-postgresql-for-ticket-persistence.md",
            }
        ),
    )


def build_source_evidence_repository() -> SourceEvidenceAdapter:
    """Build the explicit read-only source and Git allowlist for local MCP use."""
    return SourceEvidenceAdapter.from_allowlist(
        Path("."),
        paths=frozenset(
            {
                "src/incident_investigation_harness/evidence.py",
                "src/incident_investigation_harness/source_evidence.py",
            }
        ),
        refs=frozenset({"HEAD"}),
    )


def _context(scenario: str, execution_number: int) -> InvestigationContext:
    return InvestigationContext(
        incident_id=_id(f"incident-{scenario}"),
        investigation_run_id=_id(f"run-{scenario}-{execution_number}"),
    )


def _ticket(context: InvestigationContext, title: str) -> Ticket:
    return Ticket(
        id=_id(f"ticket-{context.investigation_run_id}"),
        title=title,
        description="Notification evidence collected for this Investigation Run.",
        requester_email="oncall@example.com",
        status="open",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        investigation_context=context,
    )


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:{value}")
