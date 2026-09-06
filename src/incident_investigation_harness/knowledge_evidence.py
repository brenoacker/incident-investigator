from __future__ import annotations

import uuid
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation

KnowledgeDocumentType = Literal["runbook", "adr"]


class KnowledgeEvidenceQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    query: str | None = Field(default=None, min_length=1)
    document_types: frozenset[KnowledgeDocumentType] | None = None


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    path: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    document_type: KnowledgeDocumentType


class CitedKnowledgeDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: KnowledgeDocument
    excerpt: str = Field(min_length=1)
    citation: EvidenceCitation


class KnowledgeEvidenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    documents: tuple[CitedKnowledgeDocument, ...]


class KnowledgeEvidenceRepository(Protocol):
    def query(self, query: KnowledgeEvidenceQuery) -> KnowledgeEvidenceResponse: ...

    def resolve(self, citation: EvidenceCitation) -> CitedKnowledgeDocument | None: ...
