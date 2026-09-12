"""Operational entry point for the three minimum Codex evaluations."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Iterable

from incident_investigation_harness.adapters.codex import CodexInvestigatorAdapter
from incident_investigation_harness.evidence import (
    EvidenceCitation,
    IncidentEvidenceQuery,
)
from incident_investigation_harness.fixtures import (
    build_incident_evidence_repository,
    build_knowledge_evidence_repository,
    build_source_evidence_repository,
)
from incident_investigation_harness.adapters.operational_evidence import (
    build_operational_evidence_repository,
)
from incident_investigation_harness.operational_evidence import OperationalEvidenceQuery
from incident_investigation_harness.quality_gate import EvidenceResolver, EvidenceSet
from incident_investigation_harness.runner import (
    EvaluatedRunRequest,
    EvaluatedRunResult,
    EvaluatedRunRunner,
)
from incident_investigation_harness.scenarios import ScenarioName
from incident_investigation_harness.knowledge_evidence import KnowledgeEvidenceQuery
from incident_investigation_harness.source_evidence import SourceEvidenceQuery

EVALUATED_SCENARIOS: tuple[ScenarioName, ...] = (
    ScenarioName.RETRY_STORM,
    ScenarioName.AMBIGUOUS_EVIDENCE,
    ScenarioName.PROMPT_INJECTION,
)
MAX_EVALUATION_EXECUTION_NUMBER = 10
_EVAL_NAMESPACE = uuid.NAMESPACE_URL


def request_for(scenario: ScenarioName, execution_number: int) -> EvaluatedRunRequest:
    """Create stable, non-reused identifiers for one local evaluation attempt."""
    if not 1 <= execution_number <= MAX_EVALUATION_EXECUTION_NUMBER:
        raise ValueError(
            "execution_number must be between 1 and "
            f"{MAX_EVALUATION_EXECUTION_NUMBER}"
        )
    return EvaluatedRunRequest(
        scenario=scenario,
        incident_id=uuid.uuid5(_EVAL_NAMESPACE, f"incident-investigation-harness:incident-{scenario.value}"),
        investigation_run_id=uuid.uuid5(_EVAL_NAMESPACE, f"incident-investigation-harness:run-{scenario.value}-{execution_number}"),
    )


def run_minimum_evals(
    *,
    output_dir: Path,
    execution_number: int,
    mcp_servers: dict[str, str],
    codex_executable: str = "codex",
    timeout_seconds: float = 300,
) -> tuple[EvaluatedRunResult, ...]:
    """Run the three scenarios and persist only run-scoped audit artifacts."""
    destination = output_dir / f"run-{execution_number}"
    if destination.exists():
        raise FileExistsError(f"evaluation output already exists: {destination}")
    destination.mkdir(parents=True)

    investigator = CodexInvestigatorAdapter(
        mcp_servers,
        executable=codex_executable,
        timeout_seconds=timeout_seconds,
    )
    results: list[EvaluatedRunResult] = []
    for scenario in EVALUATED_SCENARIOS:
        request = request_for(scenario, execution_number)
        result = EvaluatedRunRunner(
            investigator,
            evidence_set_factory=lambda run: evidence_set_for(run),
        ).run(request)
        _write_result(destination / scenario.value, result)
        results.append(result)

    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "execution_number": execution_number,
                "scenarios": [scenario.value for scenario in EVALUATED_SCENARIOS],
                "runs": [
                    {
                        "scenario": result.request.scenario.value,
                        "incident_id": str(result.request.incident_id),
                        "investigation_run_id": str(result.request.investigation_run_id),
                        "verdict": result.verdict,
                    }
                    for result in results
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tuple(results)


def evidence_set_for(request: EvaluatedRunRequest) -> EvidenceSet:
    """Collect the same citations exposed by the local MCP repositories."""
    context = request.context
    incident = build_incident_evidence_repository()
    operations = build_operational_evidence_repository()
    knowledge = build_knowledge_evidence_repository()
    source = build_source_evidence_repository()
    citations: list[EvidenceCitation] = []
    resolvers: list[EvidenceResolver] = []

    incident_response = incident.query(IncidentEvidenceQuery(context=context))
    citations.extend(_incident_citations(incident_response))
    resolvers.append(incident)

    operations_response = operations.query(OperationalEvidenceQuery(context=context))
    citations.extend(_operational_citations(operations_response))
    resolvers.append(operations)

    if request.scenario != ScenarioName.AMBIGUOUS_EVIDENCE:
        knowledge_response = knowledge.query(KnowledgeEvidenceQuery(context=context))
        citations.extend(item.citation for item in knowledge_response.passages)
        resolvers.append(knowledge)
        source_response = source.query(SourceEvidenceQuery(context=context))
        citations.extend(item.citation for item in source_response.artifacts)
        resolvers.append(source)

    return EvidenceSet(context=context, citations=frozenset(citations), resolvers=tuple(resolvers))


def _write_result(directory: Path, result: EvaluatedRunResult) -> None:
    directory.mkdir()
    if result.report is not None:
        (directory / "report.json").write_text(
            result.report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    (directory / "events.jsonl").write_text(result.events_jsonl + ("\n" if result.events else ""), encoding="utf-8")
    (directory / "result.json").write_text(
        json.dumps(_result_payload(result), indent=2) + "\n", encoding="utf-8"
    )


def _result_payload(result: EvaluatedRunResult) -> dict[str, object]:
    return {
        "scenario": result.request.scenario.value,
        "incident_id": str(result.request.incident_id),
        "investigation_run_id": str(result.request.investigation_run_id),
        "verdict": result.verdict,
        "quality_gate": result.quality_gate.model_dump(mode="json") if result.quality_gate else None,
        "execution_failure": result.execution_failure.model_dump(mode="json") if result.execution_failure else None,
        "isolation_probes": [probe.model_dump(mode="json") for probe in result.isolation_probes],
        "artifact_types": [artifact.artifact_type for artifact in result.artifacts],
    }


def evaluation_exit_code(results: Iterable[EvaluatedRunResult]) -> int:
    """Return a shell-friendly status: zero only when every eval is approved."""
    return 0 if all(result.approved for result in results) else 1


def _incident_citations(response: object) -> Iterable[EvidenceCitation]:
    typed = response  # kept local to avoid exposing repository implementation details
    ticket = getattr(typed, "ticket", None)
    if ticket is not None:
        yield ticket.citation
    yield from (item.citation for item in getattr(typed, "comments", ()))
    yield from (item.citation for item in getattr(typed, "timeline", ()))


def _operational_citations(response: object) -> Iterable[EvidenceCitation]:
    yield from (item.citation for item in getattr(response, "logs", ()))
    yield from (item.citation for item in getattr(response, "metrics", ()))
    yield from (item.citation for item in getattr(response, "traces", ()))


def main() -> None:  # pragma: no cover - CLI wiring is exercised by the operator
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evaluations"))
    parser.add_argument("--execution-number", type=int, required=True)
    parser.add_argument("--codex", default="codex", dest="codex_executable")
    parser.add_argument("--timeout-seconds", type=float, default=300)
    parser.add_argument("--incident-mcp-url", default="http://localhost:8001/mcp")
    parser.add_argument("--operations-mcp-url", default="http://localhost:8002/mcp")
    parser.add_argument("--knowledge-mcp-url", default="http://localhost:8003/mcp")
    parser.add_argument("--source-mcp-url", default="http://localhost:8004/mcp")
    args = parser.parse_args()
    results = run_minimum_evals(
        output_dir=args.output_dir,
        execution_number=args.execution_number,
        mcp_servers={
            "incident-mcp": args.incident_mcp_url,
            "operations-mcp": args.operations_mcp_url,
            "knowledge-mcp": args.knowledge_mcp_url,
            "source-mcp": args.source_mcp_url,
        },
        codex_executable=args.codex_executable,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "runs": len(results),
                "output_dir": str(args.output_dir / f"run-{args.execution_number}"),
                "verdicts": [
                    {"scenario": result.request.scenario.value, "verdict": result.verdict}
                    for result in results
                ],
            },
            indent=2,
        )
    )
    raise SystemExit(evaluation_exit_code(results))


if __name__ == "__main__":
    main()
