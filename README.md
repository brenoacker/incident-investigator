# Incident Investigation Harness

Local, reproducible Incident Investigation Harness. The service exposes a ticket API, read-only Evidence Providers and correlated OpenTelemetry traces/metrics for each Investigation Run.

## Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker Compose v2

## Local development

Install all dependencies, including development dependencies:

```sh
uv sync
```

Run tests and static checking:

```sh
uv run python -m pytest
uv run mypy
```

The test command measures all production code under `src/incident_investigation_harness` and fails when total coverage is below 90%.

To demonstrate the real Codex path against the Compose `incident-mcp`, authenticate Codex,
start the MCP service, and run `RUN_CODEX_INTEGRATION=1 uv run pytest tests/test_codex_real.py -m integration`.
The test is opt-in because it requires Codex credentials and a live MCP endpoint.

### Integration tests

`tests/test_postgres_integration.py` verifies that a ticket remains available after the API process restarts. It requires accessible PostgreSQL and a configured `DATABASE_URL`. In PowerShell, using the local virtual environment:

```powershell
$env:DATABASE_URL = "postgresql://ticketing:ticketing@localhost:5432/ticketing"
.\.venv\Scripts\python.exe -m pytest -m integration
```

The example assumes PostgreSQL is available at `localhost:5432`. The Compose `db` service does not publish that port to the host; use a local PostgreSQL instance or publish the port before running the integration test.

To run all tests with integration enabled:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Without `DATABASE_URL`, the integration test is marked `skipped`; the fast tests using `TicketRepositoryFake` still run.

## Docker Compose environment

Start the local API, Evidence Providers and the local observability stack:

```sh
docker compose up --build -d
```

Check availability through the Compose healthcheck or endpoints:

```sh
docker compose ps
curl http://localhost:8000/health
```

The service should be `healthy` and the endpoint should return `{"status":"ok"}`.

The local observability endpoints are Jaeger (`http://localhost:16686`), Prometheus
(`http://localhost:9090`) and Grafana (`http://localhost:3000`, anonymous read access).
Grafana provisions the `Investigation Harness` dashboard automatically. The harness
also exposes Prometheus-compatible metrics at `http://localhost:8000/metrics`.

The application exports OTLP traces and metrics to the Collector at `otel-collector:4317`.
When the Collector, Jaeger or Prometheus is unavailable, SDK export retries/drop events
in the background; business operations, Evidence Providers and the Quality Gate continue.
The Compose stack is intentionally local and ephemeral except for the PostgreSQL volume.
Use `docker compose down -v` to remove that volume when resetting local data.

Create and query a ticket:

```sh
curl -X POST http://localhost:8000/tickets \
  -H 'content-type: application/json' \
  -d '{"title":"Notification delayed","description":"Delivery latency increased.","requester_email":"oncall@example.com"}'
curl http://localhost:8000/tickets/{ticket-id}
```

Request a ticket notification. The request uses `requester_email`, starts with `pending` status and is published to the Redis `notification_requests` list:

```sh
curl -X POST http://localhost:8000/tickets/{ticket-id}/notifications
curl http://localhost:8000/notification-requests/{request-id}
```

Tickets live in the Docker `ticketing-data` volume and remain available after restarting the API process.

To stop the environment:

```sh
docker compose down
```

Every span carries the component, operation and (when available) `incident_id` and
`investigation_run_id`. Prometheus labels contain only bounded values such as scenario,
provider, operation, result and verdict; unique run identifiers are never metric labels.
JSONL events and runner artifacts remain the authoritative run-scoped audit records.

## Three minimum evaluations

The reproducible evaluation path uses the Codex CLI, not the desktop application. The
desktop is useful for dogfooding the MCPs and inspecting the local stack; the CLI is the
evaluation executor and writes the audit artifacts.

Start from a clean local environment:

```powershell
docker compose down -v
docker compose up --build -d
docker compose ps
Invoke-WebRequest http://localhost:8000/health
```

Authenticate the Codex CLI in the host environment, then run all three minimum scenarios:

```powershell
$env:PYTHONPATH = "src"
python -m incident_investigation_harness.evaluation --execution-number 1
```

The command runs `retry-storm`, `ambiguous-evidence` and `prompt-injection` through the
read-only Codex adapter. Each scenario receives a distinct `incident_id` and
`investigation_run_id`. Results are written under
`artifacts/evaluations/run-1/<scenario>/` as `result.json`, `report.json` (when a report
exists) and `events.jsonl`; `manifest.json` records the run identities and verdicts.
The command refuses to overwrite an existing run directory. To demonstrate isolation,
repeat with a new execution number and compare the two manifests:

```powershell
python -m incident_investigation_harness.evaluation --execution-number 2
Compare-Object (Get-Content artifacts/evaluations/run-1/manifest.json) `
               (Get-Content artifacts/evaluations/run-2/manifest.json)
```

Execution numbers `1` through `10` are provisioned in the local fixtures so repeated
evaluations keep the same scenario evidence shape while using a new run identity.

Inspect correlation in Jaeger by searching the `incident_id` or
`investigation_run_id` span attribute. In Prometheus use the bounded run and provider
metrics; in Grafana open the provisioned `Investigation Harness` dashboard for duration,
failures, Quality Gate activity, notification backlog and Retry Storm retries. The
identifiers intentionally remain span attributes rather than metric labels.

For a clean retry, remove the local artifacts and Compose volume before starting again:

```powershell
Remove-Item -Recurse -Force artifacts/evaluations -ErrorAction SilentlyContinue
docker compose down -v
```
