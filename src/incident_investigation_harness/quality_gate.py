from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.report import InvestigationReport

QualityGateReasonCode = Literal[
    "invalid-schema",
    "missing-citation",
    "incompatible-run",
    "citation-not-in-evidence-set",
    "citation-from-other-run",
    "unresolvable-citation",
]


class EvidenceResolver(Protocol):
    """Read-only boundary used by the evaluator to verify one citation."""

    def resolve(self, citation: EvidenceCitation) -> object | None: ...


@dataclass(frozen=True)
class EvidenceSet:
    """Immutable citations and read-only resolvers for one Investigation Run."""

    context: InvestigationContext
    citations: frozenset[EvidenceCitation]
    resolvers: tuple[EvidenceResolver, ...] = ()

    def resolve(self, citation: EvidenceCitation) -> object | None:
        for resolver in self.resolvers:
            try:
                resolved = resolver.resolve(citation)
            except ValueError:
                resolved = None
            if resolved is not None:
                return resolved
        return None


class IncidentOracle(BaseModel):
    """Private evaluation criteria, intentionally absent from investigator tools."""

    model_config = ConfigDict(frozen=True)


class QualityGateReason(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: QualityGateReasonCode
    message: str
    claim_id: str | None = None
    citation: EvidenceCitation | None = None


class QualityGateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Literal["approved", "rejected"]
    reasons: tuple[QualityGateReason, ...]

    @property
    def approved(self) -> bool:
        return self.verdict == "approved"


class QualityGate:
    """Deterministically validates report structure, identity and evidence traceability."""

    @staticmethod
    def evaluate(
        report: InvestigationReport | Mapping[str, object] | object,
        evidence_set: EvidenceSet,
        oracle: IncidentOracle,
    ) -> QualityGateResult:
        """Evaluate a report without exposing or interpreting the private Oracle."""
        del oracle
        try:
            validated_report = (
                report
                if isinstance(report, InvestigationReport)
                else InvestigationReport.model_validate(report)
            )
        except ValidationError as error:
            code: QualityGateReasonCode = (
                "missing-citation" if _has_missing_citation(error) else "invalid-schema"
            )
            return _rejected(
                QualityGateReason(
                    code=code,
                    message=(
                        "every factual claim must contain at least one citation"
                        if code == "missing-citation"
                        else "report does not conform to the Investigation Report schema"
                    ),
                )
            )

        if (
            validated_report.incident_id != evidence_set.context.incident_id
            or validated_report.investigation_run_id
            != evidence_set.context.investigation_run_id
        ):
            return _rejected(
                QualityGateReason(
                    code="incompatible-run",
                    message="report identity does not match the EvidenceSet context",
                )
            )

        reasons: list[QualityGateReason] = []
        for claim in validated_report.factual_claims:
            for citation in claim.citations:
                if citation.incident_id != evidence_set.context.incident_id or citation.investigation_run_id != evidence_set.context.investigation_run_id:
                    reasons.append(
                        QualityGateReason(
                            code="citation-from-other-run",
                            message="citation belongs to another Investigation Run",
                            claim_id=claim.id,
                            citation=citation,
                        )
                    )
                elif citation not in evidence_set.citations:
                    reasons.append(
                        QualityGateReason(
                            code="citation-not-in-evidence-set",
                            message="citation was not emitted for this EvidenceSet",
                            claim_id=claim.id,
                            citation=citation,
                        )
                    )
                elif evidence_set.resolve(citation) is None:
                    reasons.append(
                        QualityGateReason(
                            code="unresolvable-citation",
                            message="citation cannot be resolved by an Evidence Provider",
                            claim_id=claim.id,
                            citation=citation,
                        )
                    )

        return (
            _rejected(*reasons)
            if reasons
            else QualityGateResult(verdict="approved", reasons=())
        )


def _rejected(*reasons: QualityGateReason) -> QualityGateResult:
    return QualityGateResult(verdict="rejected", reasons=tuple(reasons))


def _has_missing_citation(error: ValidationError) -> bool:
    return any(
        "factual_claims" in error_location and "citations" in error_location
        for detail in error.errors()
        for error_location in (detail["loc"],)
    )
