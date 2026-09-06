from __future__ import annotations

import uuid

import pytest

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.quality_gate import (
    EvidenceSet,
    IncidentOracle,
    QualityGate,
    QualityGateReasonCode,
)
from incident_investigation_harness.report import (
    Confidence,
    EvidenceGap,
    FactualClaim,
    Hypothesis,
    InvestigationReport,
    Mitigation,
)


def test_quality_gate_approves_a_valid_report_and_resolvable_citation() -> None:
    context = _context("run-1")
    citation = _citation(context, "evidence-1")
    evidence_set = EvidenceSet(
        context=context,
        citations=frozenset({citation}),
        resolvers=(Resolver({citation}),),
    )

    result = QualityGate.evaluate(_report(context, citation), evidence_set, IncidentOracle())

    assert result.approved
    assert result.verdict == "approved"
    assert result.reasons == ()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"schema_version": "not-a-version"}, "invalid-schema"),
        ("not-a-report", "invalid-schema"),
    ],
)
def test_quality_gate_rejects_invalid_schema(
    payload: object, expected: QualityGateReasonCode
) -> None:
    context = _context("run-1")
    evidence_set = EvidenceSet(context=context, citations=frozenset())

    result = QualityGate.evaluate(payload, evidence_set, IncidentOracle())

    assert not result.approved
    assert [reason.code for reason in result.reasons] == [expected]


def test_quality_gate_rejects_a_factual_claim_without_a_citation() -> None:
    context = _context("run-1")
    payload = _report(context, None).model_dump(mode="json")
    payload["factual_claims"] = [
        {"id": "claim-1", "statement": "Unsupported fact.", "citations": []}
    ]

    result = QualityGate.evaluate(
        payload, EvidenceSet(context=context, citations=frozenset()), IncidentOracle()
    )

    assert _codes(result) == ["missing-citation"]


def test_evidence_set_is_immutable() -> None:
    evidence_set = EvidenceSet(context=_context("run-1"), citations=frozenset())

    with pytest.raises(AttributeError):
        evidence_set.context = _context("run-2")  # type: ignore[misc]


def test_quality_gate_rejects_incompatible_report_identity() -> None:
    report_context = _context("run-1")
    evidence_context = _context("run-2")
    evidence_set = EvidenceSet(context=evidence_context, citations=frozenset())

    result = QualityGate.evaluate(
        _report(report_context, None), evidence_set, IncidentOracle()
    )

    assert _codes(result) == ["incompatible-run"]


def test_quality_gate_rejects_an_invented_citation() -> None:
    context = _context("run-1")
    citation = _citation(context, "invented")
    evidence_set = EvidenceSet(context=context, citations=frozenset())

    result = QualityGate.evaluate(_report(context, citation), evidence_set, IncidentOracle())

    assert _codes(result) == ["citation-not-in-evidence-set"]


def test_quality_gate_rejects_a_citation_from_another_run() -> None:
    context = _context("run-1")
    other_context = _context("run-2")
    citation = _citation(other_context, "other-run")
    evidence_set = EvidenceSet(context=context, citations=frozenset({citation}))

    result = QualityGate.evaluate(_report(context, citation), evidence_set, IncidentOracle())

    assert _codes(result) == ["citation-from-other-run"]


def test_quality_gate_rejects_a_citation_that_cannot_be_resolved() -> None:
    context = _context("run-1")
    citation = _citation(context, "missing")
    evidence_set = EvidenceSet(
        context=context, citations=frozenset({citation}), resolvers=(Resolver(),)
    )

    result = QualityGate.evaluate(_report(context, citation), evidence_set, IncidentOracle())

    assert _codes(result) == ["unresolvable-citation"]


def _report(
    context: InvestigationContext, citation: EvidenceCitation | None
) -> InvestigationReport:
    claims = (
        FactualClaim(
            id="claim-1",
            statement="The provider returned 429 responses.",
            citations=(citation,) if citation else (),
        ),
    ) if citation else ()
    return InvestigationReport(
        schema_version="1.0",
        incident_id=context.incident_id,
        investigation_run_id=context.investigation_run_id,
        impact="Notifications were delayed.",
        timeline=(),
        factual_claims=claims,
        hypotheses=(Hypothesis(statement="A dependency failed."),),
        confidence=Confidence(level="medium", rationale="Evidence is available."),
        suggested_mitigation=Mitigation(
            action="Investigate the dependency.", rationale="Confirm the failure mode."
        ),
        evidence_gaps=(
            EvidenceGap(description="Policy is unknown.", needed_evidence="Provider policy"),
        ),
    )


def _context(run: str) -> InvestigationContext:
    return InvestigationContext(
        incident_id=uuid.uuid5(uuid.NAMESPACE_URL, "quality-gate-incident"),
        investigation_run_id=uuid.uuid5(uuid.NAMESPACE_URL, f"quality-gate-{run}"),
    )


def _citation(context: InvestigationContext, value: str) -> EvidenceCitation:
    return EvidenceCitation(
        provider="operations-mcp",
        incident_id=context.incident_id,
        investigation_run_id=context.investigation_run_id,
        evidence_type="operational-log",
        evidence_id=uuid.uuid5(uuid.NAMESPACE_URL, f"quality-gate-{value}"),
    )


def _codes(result: object) -> list[str]:
    return [reason.code for reason in result.reasons]  # type: ignore[attr-defined]


class Resolver:
    def __init__(self, citations: set[EvidenceCitation] | None = None) -> None:
        self._citations = citations or set()

    def resolve(self, citation: EvidenceCitation) -> EvidenceCitation | None:
        return citation if citation in self._citations else None
