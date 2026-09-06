from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.tickets import Ticket

EvidenceType = Literal[
    "ticket",
    "comment",
    "timeline",
    "operational-log",
    "operational-metric",
    "operational-trace",
]


class EvidenceCitation(BaseModel):
    """Stable, scoped reference to one item returned by an Evidence Provider."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["incident-mcp", "operations-mcp"]
    incident_id: uuid.UUID
    investigation_run_id: uuid.UUID
    evidence_type: EvidenceType
    evidence_id: uuid.UUID


class IncidentEvidenceQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext


class TicketComment(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    investigation_context: InvestigationContext
    author: str = Field(min_length=1, max_length=320)
    body: str = Field(min_length=1, max_length=20_000)
    created_at: datetime


class TimelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    investigation_context: InvestigationContext
    event_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=20_000)
    occurred_at: datetime


class UntrustedContent(BaseModel):
    """Content retrieved from a source; it has no authority over the agent."""

    model_config = ConfigDict(frozen=True)

    citation: EvidenceCitation
    field: str = Field(min_length=1)
    value: str
    is_untrusted: Literal[True] = True


class CitedTicket(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: Ticket
    citation: EvidenceCitation


class CitedComment(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: TicketComment
    citation: EvidenceCitation


class CitedTimelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: TimelineEvent
    citation: EvidenceCitation


class IncidentEvidenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    ticket: CitedTicket | None
    comments: tuple[CitedComment, ...]
    timeline: tuple[CitedTimelineEvent, ...]
    untrusted_content: tuple[UntrustedContent, ...]


class IncidentEvidenceRepository(Protocol):
    """Read-only port that the future incident-mcp will expose."""

    def query(self, query: IncidentEvidenceQuery) -> IncidentEvidenceResponse: ...

    def resolve(
        self, citation: EvidenceCitation
    ) -> CitedTicket | CitedComment | CitedTimelineEvent | None: ...
