from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.evidence import EvidenceCitation

REPORT_SCHEMA_VERSION = "1.0"


class FactualClaim(BaseModel):
    """A factual statement that can be checked against Evidence Providers."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=1, max_length=20_000)
    citations: tuple[EvidenceCitation, ...] = Field(min_length=1)


class TimelineEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    occurred_at: datetime
    description: str = Field(min_length=1, max_length=20_000)
    factual_claim_ids: tuple[str, ...] = ()


class Hypothesis(BaseModel):
    """A possible explanation, kept distinct from cited factual claims."""

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1, max_length=20_000)
    supporting_claim_ids: tuple[str, ...] = ()


class Confidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: Literal["low", "medium", "high"]
    rationale: str = Field(min_length=1, max_length=20_000)


class Mitigation(BaseModel):
    """A recommended safe next action; it is not an operational command."""

    model_config = ConfigDict(frozen=True)

    action: str = Field(min_length=1, max_length=20_000)
    rationale: str = Field(min_length=1, max_length=20_000)


class EvidenceGap(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1, max_length=20_000)
    needed_evidence: str = Field(min_length=1, max_length=20_000)


class InvestigationReport(BaseModel):
    """Versioned, auditable output of one Read-Only Investigation."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"]
    incident_id: uuid.UUID
    investigation_run_id: uuid.UUID
    impact: str = Field(min_length=1, max_length=20_000)
    timeline: tuple[TimelineEntry, ...]
    factual_claims: tuple[FactualClaim, ...]
    hypotheses: tuple[Hypothesis, ...]
    probable_cause: Hypothesis | None = None
    confidence: Confidence
    suggested_mitigation: Mitigation
    evidence_gaps: tuple[EvidenceGap, ...]
