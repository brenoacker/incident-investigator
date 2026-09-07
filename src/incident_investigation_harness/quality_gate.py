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
    "scenario-criteria-not-met",
    "unsupported-factual-claim",
    "incompatible-conclusion",
    "incomplete-mitigation",
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

    version: str = "base-1"

    def evaluate_report(
        self,
        report: InvestigationReport,
        evidence_set: EvidenceSet,
    ) -> tuple[QualityGateReason, ...]:
        """Return private scenario reasons; the base oracle has no criteria."""
        del report, evidence_set
        return ()


class RetryStormOracle(IncidentOracle):
    """Versioned, evaluator-only criteria for the sufficient Retry Storm case."""

    version: str = "retry-storm-1"
    required_providers: frozenset[str] = frozenset(
        {"incident-mcp", "operations-mcp", "knowledge-mcp", "source-mcp"}
    )
    required_facts: tuple[str, ...] = ("429", "retry", "backlog", "latency")
    mitigation_terms: tuple[str, ...] = ("backoff", "attempt", "jitter")
    incompatible_terms: tuple[str, ...] = (
        "no retries",
        "database is the cause",
        "postgres is the cause",
        "traffic spike is the cause",
    )

    def evaluate_report(
        self,
        report: InvestigationReport,
        evidence_set: EvidenceSet,
    ) -> tuple[QualityGateReason, ...]:
        reasons: list[QualityGateReason] = []
        resolved = {
            citation: evidence_set.resolve(citation)
            for claim in report.factual_claims
            for citation in claim.citations
        }
        providers = {citation.provider for citation in resolved}
        missing_providers = self.required_providers - providers
        if missing_providers:
            reasons.append(
                QualityGateReason(
                    code="scenario-criteria-not-met",
                    message=(
                        "report must cite all Evidence Providers; missing: "
                        + ", ".join(sorted(missing_providers))
                    ),
                )
            )

        for fact in self.required_facts:
            matching_claims = [
                claim
                for claim in report.factual_claims
                if _fact_matches(fact, claim.statement)
            ]
            supported = any(
                _fact_matches(fact, _evidence_text(resolved[citation]))
                for claim in matching_claims
                for citation in claim.citations
                if resolved[citation] is not None
            )
            if not matching_claims or not supported:
                reasons.append(
                    QualityGateReason(
                        code="unsupported-factual-claim",
                        message=f"Retry Storm fact is missing or unsupported: {fact}",
                    )
                )

        probable_cause = report.probable_cause.statement.casefold() if report.probable_cause else ""
        if any(term in probable_cause for term in self.incompatible_terms):
            reasons.append(
                QualityGateReason(
                    code="incompatible-conclusion",
                    message="probable cause conflicts with the Retry Storm oracle",
                )
            )
        if not probable_cause or not any(
            term in probable_cause for term in ("retry", "rate limit", "429")
        ):
            reasons.append(
                QualityGateReason(
                    code="incompatible-conclusion",
                    message="probable cause must explain rate limiting and inadequate retries",
                )
            )

        mitigation = (
            report.suggested_mitigation.action + " " + report.suggested_mitigation.rationale
        ).casefold()
        missing_terms = [term for term in self.mitigation_terms if term not in mitigation]
        if missing_terms:
            reasons.append(
                QualityGateReason(
                    code="incomplete-mitigation",
                    message="mitigation must recommend backoff, an attempt limit and jitter",
                )
            )
        if any(term in mitigation for term in ("execute now", "restart service", "apply change")):
            reasons.append(
                QualityGateReason(
                    code="incomplete-mitigation",
                    message="mitigation must be a recommendation and must not execute an action",
                )
            )
        return tuple(reasons)


class AmbiguousEvidenceOracle(IncidentOracle):
    """Evaluator-only criteria for a run whose evidence cannot establish a cause."""

    version: str = "ambiguous-evidence-1"
    required_confidence: Literal["low"] = "low"
    minimum_hypotheses: int = 2
    relevant_gap_terms: tuple[str, ...] = (
        "provider",
        "retry",
        "queue",
        "worker",
        "log",
        "metric",
        "trace",
    )
    alternative_terms: tuple[str, ...] = (
        "alternative",
        "plausible",
        "possible",
        "may",
        "might",
        "could",
    )

    def evaluate_report(
        self,
        report: InvestigationReport,
        evidence_set: EvidenceSet,
    ) -> tuple[QualityGateReason, ...]:
        del evidence_set
        reasons: list[QualityGateReason] = []
        if report.confidence.level != self.required_confidence:
            reasons.append(
                QualityGateReason(
                    code="scenario-criteria-not-met",
                    message="ambiguous evidence requires low confidence",
                )
            )
        distinct_hypotheses = {
            hypothesis.statement.casefold().strip() for hypothesis in report.hypotheses
        }
        has_plausible_alternative = any(
            any(term in hypothesis.casefold() for term in self.alternative_terms)
            for hypothesis in distinct_hypotheses
        )
        if (
            len(distinct_hypotheses) < self.minimum_hypotheses
            or not has_plausible_alternative
        ):
            reasons.append(
                QualityGateReason(
                    code="scenario-criteria-not-met",
                    message="ambiguous evidence requires at least one alternative hypothesis",
                )
            )
        gap_text = " ".join(
            f"{gap.description} {gap.needed_evidence}" for gap in report.evidence_gaps
        ).casefold()
        if not report.evidence_gaps or not any(
            term in gap_text for term in self.relevant_gap_terms
        ):
            reasons.append(
                QualityGateReason(
                    code="scenario-criteria-not-met",
                    message="report must request relevant next evidence for the uncertainty",
                )
            )
        if report.probable_cause is not None:
            reasons.append(
                QualityGateReason(
                    code="incompatible-conclusion",
                    message="ambiguous evidence does not support a categorical probable cause",
                )
            )
        return tuple(reasons)


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
        try:
            validated_report = InvestigationReport.model_validate(
                report.model_dump(mode="json")
                if isinstance(report, InvestigationReport)
                else report
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

        reasons.extend(oracle.evaluate_report(validated_report, evidence_set))
        return _rejected(*reasons) if reasons else QualityGateResult(verdict="approved", reasons=())


def _rejected(*reasons: QualityGateReason) -> QualityGateResult:
    return QualityGateResult(verdict="rejected", reasons=tuple(reasons))


def _has_missing_citation(error: ValidationError) -> bool:
    return any(
        "factual_claims" in error_location and "citations" in error_location
        for detail in error.errors()
        for error_location in (detail["loc"],)
    )


def _evidence_text(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, BaseModel):
        return value.model_dump_json().casefold()
    return str(value).casefold()


def _fact_matches(fact: str, text: str) -> bool:
    normalized = text.casefold()
    if fact == "429":
        return "429" in normalized or "rate limit" in normalized or "rate-limited" in normalized
    if fact == "retry":
        return any(term in normalized for term in ("retry", "attempt"))
    if fact == "backlog":
        return "backlog" in normalized or "queue" in normalized
    if fact == "latency":
        return any(term in normalized for term in ("latency", "p99", "degradation"))
    return fact in normalized
