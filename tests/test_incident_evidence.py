from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from incident_investigation_harness.adapters.incident_evidence import (
    IncidentEvidenceRepositoryFake,
)
from incident_investigation_harness.fixtures import build_incident_evidence_repository
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import (
    EvidenceCitation,
    IncidentEvidenceQuery,
    TimelineEvent,
    TicketComment,
)
from incident_investigation_harness.tickets import Ticket


def test_incident_evidence_contract_is_scoped_cited_and_read_only() -> None:
    first = _context(1)
    second = _context(2)
    first_ticket = _ticket(first, "First incident")
    second_ticket = _ticket(second, "Second incident")
    first_comment = TicketComment(
        id=uuid.uuid4(),
        ticket_id=first_ticket.id,
        investigation_context=first,
        author="oncall@example.com",
        body="The provider started returning 429.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    first_event = TimelineEvent(
        id=uuid.uuid4(),
        investigation_context=first,
        event_type="observation",
        description="Notification latency increased.",
        occurred_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
    )
    repository = IncidentEvidenceRepositoryFake(
        tickets=[first_ticket, second_ticket],
        comments=[first_comment],
        timeline=[first_event],
    )

    result = repository.query(IncidentEvidenceQuery(context=first))
    repeated = repository.query(IncidentEvidenceQuery(context=first))
    other = repository.query(IncidentEvidenceQuery(context=second))

    assert result.ticket is not None
    assert result.ticket.item.id == first_ticket.id
    assert result.ticket.citation == repeated.ticket.citation
    assert result.ticket.citation.evidence_id == first_ticket.id
    assert result.ticket.citation.provider == "incident-mcp"
    assert result.comments[0].citation.evidence_id == first_comment.id
    assert result.timeline[0].citation.evidence_id == first_event.id
    assert all(content.is_untrusted for content in result.untrusted_content)
    assert any(
        content.citation == result.comments[0].citation
        for content in result.untrusted_content
    )
    assert other.ticket is not None
    assert other.ticket.item.id == second_ticket.id
    assert other.comments == ()
    assert other.timeline == ()

    resolved = repository.resolve(result.comments[0].citation)
    assert resolved is not None
    assert resolved.citation == result.comments[0].citation
    incompatible = result.comments[0].citation.model_copy(
        update={"evidence_type": "timeline"}
    )
    assert repository.resolve(incompatible) is None

    with pytest.raises(AttributeError):
        getattr(repository, "create")


def test_prompt_injection_fixture_exposes_malicious_content_as_untrusted_evidence() -> None:
    context = InvestigationContext(
        incident_id=uuid.uuid5(uuid.NAMESPACE_URL, "incident-investigation-harness:incident-prompt-injection"),
        investigation_run_id=uuid.uuid5(uuid.NAMESPACE_URL, "incident-investigation-harness:run-prompt-injection-1"),
    )
    result = build_incident_evidence_repository().query(IncidentEvidenceQuery(context=context))
    assert result.ticket is not None
    assert any(
        "ignore previous instructions" in content.value.casefold()
        and content.is_untrusted
        for content in result.untrusted_content
    )


def _context(number: int) -> InvestigationContext:
    return InvestigationContext(
        incident_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"incident-{number}"),
        investigation_run_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"run-{number}"),
    )


def _ticket(context: InvestigationContext, title: str) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        title=title,
        description="A ticket description.",
        requester_email="oncall@example.com",
        status="open",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        investigation_context=context,
    )
