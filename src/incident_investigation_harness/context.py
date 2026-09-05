from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class InvestigationContext(BaseModel):
    """Identity propagated through one Incident Investigation Run."""

    model_config = ConfigDict(frozen=True)

    incident_id: uuid.UUID
    investigation_run_id: uuid.UUID
