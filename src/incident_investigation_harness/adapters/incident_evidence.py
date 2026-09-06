from __future__ import annotations

import uuid
from typing import Iterable

from incident_investigation_harness.evidence import (
    CitedComment,
    CitedTimelineEvent,
    CitedTicket,
    EvidenceCitation,
    IncidentEvidenceQuery,
    IncidentEvidenceResponse,
    TimelineEvent,
    TicketComment,
    UntrustedContent,
    EvidenceType,
)
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.tickets import Ticket


class InMemoryIncidentEvidenceRepository:
    """Read-only evidence source for deterministic provider fixtures."""

    def __init__(
        self,
        *,
        tickets: Iterable[Ticket] = (),
        comments: Iterable[TicketComment] = (),
        timeline: Iterable[TimelineEvent] = (),
    ) -> None:
        self._tickets = tuple(tickets)
        self._comments = tuple(comments)
        self._timeline = tuple(timeline)

    def query(self, query: IncidentEvidenceQuery) -> IncidentEvidenceResponse:
        context = query.context
        ticket = next(
            (
                item
                for item in self._tickets
                if item.investigation_context == context
            ),
            None,
        )
        comments = tuple(
            item for item in self._comments if item.investigation_context == context
        )
        timeline = tuple(
            item for item in self._timeline if item.investigation_context == context
        )

        cited_ticket = self._cite_ticket(ticket) if ticket else None
        cited_comments = tuple(self._cite_comment(item) for item in comments)
        cited_timeline = tuple(self._cite_timeline(item) for item in timeline)
        untrusted_content = tuple(
            content
            for cited in (
                *((cited_ticket,) if cited_ticket else ()),
                *cited_comments,
                *cited_timeline,
            )
            for content in self._untrusted_content(cited)
        )

        return IncidentEvidenceResponse(
            context=context,
            ticket=cited_ticket,
            comments=cited_comments,
            timeline=cited_timeline,
            untrusted_content=untrusted_content,
        )

    def resolve(
        self, citation: EvidenceCitation
    ) -> CitedTicket | CitedComment | CitedTimelineEvent | None:
        if citation.provider != "incident-mcp":
            return None
        for ticket in self._tickets:
            if (
                citation.evidence_type == "ticket"
                and
                ticket.id == citation.evidence_id
                and ticket.investigation_context == self._context(citation)
            ):
                return self._cite_ticket(ticket)
        for comment in self._comments:
            if (
                citation.evidence_type == "comment"
                and
                comment.id == citation.evidence_id
                and comment.investigation_context == self._context(citation)
            ):
                return self._cite_comment(comment)
        for event in self._timeline:
            if (
                citation.evidence_type == "timeline"
                and
                event.id == citation.evidence_id
                and event.investigation_context == self._context(citation)
            ):
                return self._cite_timeline(event)
        return None

    @staticmethod
    def _context(citation: EvidenceCitation) -> InvestigationContext:
        return InvestigationContext(
            incident_id=citation.incident_id,
            investigation_run_id=citation.investigation_run_id,
        )

    @staticmethod
    def _citation(
        item: Ticket | TicketComment | TimelineEvent,
        context: InvestigationContext,
        evidence_type: EvidenceType,
    ) -> EvidenceCitation:
        return EvidenceCitation(
            provider="incident-mcp",
            incident_id=context.incident_id,
            investigation_run_id=context.investigation_run_id,
            evidence_type=evidence_type,
            evidence_id=item.id,
        )

    def _cite_ticket(self, item: Ticket) -> CitedTicket:
        return CitedTicket(
            item=item,
            citation=self._citation(item, item.investigation_context, "ticket"),
        )

    def _cite_comment(self, item: TicketComment) -> CitedComment:
        return CitedComment(
            item=item,
            citation=self._citation(item, item.investigation_context, "comment"),
        )

    def _cite_timeline(self, item: TimelineEvent) -> CitedTimelineEvent:
        return CitedTimelineEvent(
            item=item,
            citation=self._citation(item, item.investigation_context, "timeline"),
        )

    @staticmethod
    def _untrusted_content(
        cited: CitedTicket | CitedComment | CitedTimelineEvent,
    ) -> tuple[UntrustedContent, ...]:
        if isinstance(cited, CitedTicket):
            return (
                UntrustedContent(
                    citation=cited.citation, field="title", value=cited.item.title
                ),
                UntrustedContent(
                    citation=cited.citation,
                    field="description",
                    value=cited.item.description,
                ),
            )
        if isinstance(cited, CitedComment):
            return (
                UntrustedContent(
                    citation=cited.citation, field="body", value=cited.item.body
                ),
            )
        if isinstance(cited, CitedTimelineEvent):
            return (
                UntrustedContent(
                    citation=cited.citation,
                    field="description",
                    value=cited.item.description,
                ),
            )
        return ()
