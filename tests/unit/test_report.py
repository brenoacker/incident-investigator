from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.report import (
    Confidence,
    EvidenceGap,
    FactualClaim,
    Hypothesis,
    InvestigationReport,
    Mitigation,
    TimelineEntry,
)


def test_investigation_report_validates_complete_report() -> None:
    context = _ids()
    citation = _citation(context)

    report = InvestigationReport(
        schema_version="1.0",
        incident_id=context["incident_id"],
        investigation_run_id=context["investigation_run_id"],
        impact="Notification delivery was delayed for customers.",
        timeline=(
            TimelineEntry(
                occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                description="The provider began returning 429 responses.",
                factual_claim_ids=("claim-1",),
            ),
        ),
        factual_claims=(
            FactualClaim(
                id="claim-1",
                statement="The provider returned 429 responses.",
                citations=(citation,),
            ),
        ),
        hypotheses=(
            Hypothesis(
                statement="Retries without backoff amplified the dependency failure.",
                supporting_claim_ids=("claim-1",),
            ),
        ),
        probable_cause=Hypothesis(
            statement="Immediate retries caused a retry storm.",
            supporting_claim_ids=("claim-1",),
        ),
        confidence=Confidence(level="high", rationale="Multiple independent signals agree."),
        suggested_mitigation=Mitigation(
            action="Add bounded exponential backoff and jitter.",
            rationale="This limits amplification during rate limiting.",
        ),
        evidence_gaps=(EvidenceGap(description="The dependency's rate-limit policy is unknown.", needed_evidence="Provider configuration"),),
    )

    assert report.model_dump(mode="json")["schema_version"] == "1.0"
    assert report.factual_claims[0].citations[0] == citation


def test_investigation_report_allows_calibrated_uncertainty_without_probable_cause() -> None:
    context = _ids()
    report = InvestigationReport(
        schema_version="1.0",
        incident_id=context["incident_id"],
        investigation_run_id=context["investigation_run_id"],
        impact="Some notifications were delayed.",
        timeline=(),
        factual_claims=(),
        hypotheses=(
            Hypothesis(statement="A dependency failure may be involved."),
            Hypothesis(statement="Queue contention is an alternative explanation."),
        ),
        confidence=Confidence(level="low", rationale="Available evidence is insufficient."),
        suggested_mitigation=Mitigation(
            action="Collect provider responses and queue metrics.",
            rationale="These observations distinguish the hypotheses.",
        ),
        evidence_gaps=(EvidenceGap(description="No provider response data is available.", needed_evidence="Provider logs"),),
    )

    assert report.probable_cause is None
    assert report.confidence.level == "low"


@pytest.mark.parametrize(
    "changes",
    [
        {"impact": None},
        {"factual_claims": ({"id": "claim-1", "statement": "Unsupported", "citations": ()},)},
        {"factual_claims": ({"id": "claim-1", "statement": "Malformed", "citations": ({"provider": "not-a-provider"},)},)},
    ],
)
def test_investigation_report_rejects_missing_required_fields_and_malformed_citations(
    changes: dict[str, object],
) -> None:
    context = _ids()
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "incident_id": context["incident_id"],
        "investigation_run_id": context["investigation_run_id"],
        "impact": "Impact",
        "timeline": (),
        "factual_claims": (),
        "hypotheses": (),
        "confidence": {"level": "medium", "rationale": "Some evidence exists."},
        "suggested_mitigation": {"action": "Investigate", "rationale": "Evidence is incomplete."},
        "evidence_gaps": (),
    }
    payload.update(changes)

    with pytest.raises(ValidationError):
        InvestigationReport.model_validate(payload)


def test_investigation_report_rejects_missing_required_section() -> None:
    context = _ids()
    payload = {
        "schema_version": "1.0",
        "incident_id": context["incident_id"],
        "investigation_run_id": context["investigation_run_id"],
        "timeline": (),
        "factual_claims": (),
        "hypotheses": (),
        "confidence": {"level": "medium", "rationale": "Some evidence exists."},
        "suggested_mitigation": {"action": "Investigate", "rationale": "Evidence is incomplete."},
        "evidence_gaps": (),
    }

    with pytest.raises(ValidationError):
        InvestigationReport.model_validate(payload)


def _ids() -> dict[str, uuid.UUID]:
    return {
        "incident_id": uuid.uuid4(),
        "investigation_run_id": uuid.uuid4(),
    }


def _citation(context: dict[str, uuid.UUID]) -> EvidenceCitation:
    return EvidenceCitation(
        provider="incident-mcp",
        incident_id=context["incident_id"],
        investigation_run_id=context["investigation_run_id"],
        evidence_type="ticket",
        evidence_id=uuid.uuid4(),
    )
