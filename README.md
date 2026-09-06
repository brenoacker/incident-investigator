# Incident Investigation Harness

Local, reproducible foundation for the Incident Investigation Harness. The service exposes a ticket API and persists records in local PostgreSQL; the worker, MCPs and other flows are being added incrementally.

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
uv run pytest
uv run mypy
```

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

Start the local API and PostgreSQL:

```sh
docker compose up --build -d
```

Check availability through the Compose healthcheck or endpoints:

```sh
docker compose ps
curl http://localhost:8000/health
```

The service should be `healthy` and the endpoint should return `{"status":"ok"}`.

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
