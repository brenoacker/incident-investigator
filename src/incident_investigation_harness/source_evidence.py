from __future__ import annotations

import uuid
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation

SourceEvidenceType = Literal["source-code", "source-diff", "git-history"]


class SourceEvidenceQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    query: str | None = Field(default=None, min_length=1)
    evidence_types: frozenset[SourceEvidenceType] | None = None
    paths: frozenset[str] | None = None
    refs: frozenset[str] | None = None


class SourceArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    artifact_type: SourceEvidenceType
    path: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    content: str


class CitedSourceArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: SourceArtifact
    excerpt: str = Field(min_length=1)
    citation: EvidenceCitation


class SourceEvidenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    artifacts: tuple[CitedSourceArtifact, ...]


class SourceEvidenceRepository(Protocol):
    def query(self, query: SourceEvidenceQuery) -> SourceEvidenceResponse: ...

    def resolve(self, citation: EvidenceCitation) -> CitedSourceArtifact | None: ...
