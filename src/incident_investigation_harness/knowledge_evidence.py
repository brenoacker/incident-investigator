from __future__ import annotations

import uuid
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation

KnowledgeDocumentType = Literal["runbook", "adr"]
MatchKind = Literal["lexical", "semantic", "hybrid"]
RetrievalMode = Literal["hybrid", "lexical"]


class KnowledgeEvidenceQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    query: str | None = Field(default=None, min_length=1)
    document_types: frozenset[KnowledgeDocumentType] | None = None
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    path: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    document_type: KnowledgeDocumentType


class KnowledgePassage(BaseModel):
    model_config = ConfigDict(frozen=True)

    passage_id: uuid.UUID
    document_id: uuid.UUID
    revision_id: str = Field(min_length=64, max_length=64)
    path: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document_type: KnowledgeDocumentType
    text: str = Field(min_length=1)
    ordinal: int = Field(ge=0)


class CitedKnowledgePassage(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: KnowledgePassage
    relevance_score: float = Field(ge=0, le=1)
    match_kind: MatchKind
    citation: EvidenceCitation
    is_untrusted: Literal[True] = True


class KnowledgeEvidenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    passages: tuple[CitedKnowledgePassage, ...]
    retrieval_mode: RetrievalMode
    degraded: bool = False
    degraded_reason: str | None = None


class KnowledgeEvidenceRepository(Protocol):
    def query(self, query: KnowledgeEvidenceQuery) -> KnowledgeEvidenceResponse: ...

    def resolve(self, citation: EvidenceCitation) -> CitedKnowledgePassage | None: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    model_revision: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...
