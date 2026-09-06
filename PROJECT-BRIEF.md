# Incident Investigation Harness for Codex

## Objective

Demonstrate end-to-end AI Engineering with a local, reproducible environment in which Codex investigates incidents in a simulated Ticketing SaaS. The system produces auditable recommendations; the MVP does not execute mitigation.

## Problem

Incident evidence is scattered across tickets, logs, traces, metrics, runbooks and code. The harness gives Codex privilege-limited sources and requires an evidence-based report, making quality, security and operations repeatable to evaluate.

## Decided principles

- Codex is the harness; we do not build a separate chat agent.
- The entire product environment runs locally through Docker Compose.
- Codex CLI runs evaluations; the desktop application is for development and dogfooding.
- Each evaluated run uses an isolated agent workspace. Code, evidence and oracles stay outside it; only code and evidence enter through read-only MCPs.
- The MVP is read-only: it investigates and recommends, but does not apply changes or operational actions.
- Operational evidence is untrusted and cannot change the agent's instructions or permissions.
- A report passes only when each relevant factual claim has verifiable Evidence Citations.
- The Incident Oracle is inaccessible to Codex during investigation.
- The deterministic Quality Gate is the MVP authority.

## Investigation flow

```text
Incident ticket
  -> Codex CLI + investigation skill
  -> incident-mcp | operations-mcp | knowledge-mcp | source-mcp
  -> Structured Investigation Report with citations
  -> Deterministic Quality Gate against the Incident Oracle
  -> Results, events and metrics in the local observability stack
```

## System under investigation

The Ticketing SaaS receives tickets and sends asynchronous notifications. Its initial components are:

- `ticket-api`: FastAPI + Pydantic API for creating tickets and notification requests.
- `notification-worker`: asynchronous Python worker that consumes the queue.
- PostgreSQL: tickets and operational state.
- Redis: queue and backlog.
- `notification-provider`: local dependency that can return controlled `429` responses.

A failure injector and traffic generator create deterministic incidents.

## MVP: first vertical slice

### Main scenario

A notification dependency returns `429`. The worker retries without adequate backoff, limits or jitter. The pressure amplifies the error, increases the queue and degrades p99 latency.

### Evidence Providers via MCP

- `incident-mcp`: ticket, comments and timeline.
- `operations-mcp`: logs, metrics and traces; read-only.
- `knowledge-mcp`: relevant runbooks and ADRs.
- `source-mcp`: code, diff and Git history.

### Required report

The Investigation Report contains impact, an evidence-based timeline, hypotheses, probable cause, confidence, suggested mitigation, evidence gaps and Evidence Citations.

### Minimum evaluations

1. Sufficient-evidence Retry Storm: diagnose it and recommend retry controls.
2. Ambiguous evidence: state calibrated uncertainty and request the next relevant evidence.
3. Prompt injection in the ticket: ignore the malicious instruction and keep the investigation safe.

## Core technology

- Python with `uv`, Pydantic, `pytest`, `asyncio` and type checking.
- Modular monorepo with one `pyproject.toml`; API, worker, MCPs, simulator and runner have separate modules and entry points.
- Codex CLI in a read-only sandbox, with JSONL event output and a structured report schema.
- OpenTelemetry + Collector + Jaeger for traces; Prometheus + Grafana for metrics and dashboards.
- Docker Compose for the application, MCPs, observability stack and fixtures.

Each Investigation Run receives `incident_id` and `investigation_run_id`, which are propagated through MCPs, logs, spans and the report. The Codex adapter also injects them into the effective investigation context, allowing bounded MCP queries without requiring the investigator to discover opaque UUIDs.

## Planned growth after the MVP

1. Advanced retrieval in `knowledge-mcp`: embeddings, chunking, hybrid search, reranking and recall@k metrics.
2. Context engineering: retrieved memory, instruction caching and compaction for long investigations.
3. More scenarios: poison message, invalid configuration/cache, stale retrieval index and dependency failures.
4. Broader evaluation: regression tests, mutation tests and LLM-as-a-judge only as a complementary metric.
5. Human-approved action mode with separate, reversible and audited tools.
6. UI for opening incidents and comparing Investigation Runs, only after flows stabilize.

The project demonstrates MCP and tool use, agents and skills, retrieval, context engineering, deterministic evaluations, prompt-injection guardrails, agent observability, operational quality, resilience and production Python instead of an isolated document-chat demo.
