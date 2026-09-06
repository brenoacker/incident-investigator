from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation

OperationalEvidenceType = Literal[
    "operational-log", "operational-metric", "operational-trace"
]


class OperationalEvidenceQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    evidence_types: frozenset[OperationalEvidenceType] | None = None
    operation: str | None = Field(default=None, min_length=1)


class OperationalLog(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    investigation_context: InvestigationContext
    timestamp: datetime
    level: Literal["INFO", "WARN", "ERROR"]
    message: str = Field(min_length=1)
    values: dict[str, int | float | str]


class OperationalMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    investigation_context: InvestigationContext
    timestamp: datetime
    name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    operation: str = Field(min_length=1)


class OperationalTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    investigation_context: InvestigationContext
    timestamp: datetime
    operation: str = Field(min_length=1)
    duration_ms: float = Field(ge=0)
    status_code: int = Field(ge=100, le=599)
    values: dict[str, int | float | str]


class CitedOperationalLog(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: OperationalLog
    citation: EvidenceCitation


class CitedOperationalMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: OperationalMetric
    citation: EvidenceCitation


class CitedOperationalTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: OperationalTrace
    citation: EvidenceCitation


class OperationalEvidenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    logs: tuple[CitedOperationalLog, ...]
    metrics: tuple[CitedOperationalMetric, ...]
    traces: tuple[CitedOperationalTrace, ...]


class OperationalEvidenceRepository(Protocol):
    def query(self, query: OperationalEvidenceQuery) -> OperationalEvidenceResponse: ...

    def resolve(
        self, citation: EvidenceCitation
    ) -> CitedOperationalLog | CitedOperationalMetric | CitedOperationalTrace | None: ...
