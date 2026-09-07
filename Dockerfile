FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY docs/adr/0001-postgresql-for-ticket-persistence.md ./docs/adr/
COPY docs/scenarios/retry-storm-latency.md ./docs/scenarios/
RUN git init \
    && git config user.name "Incident Investigation Harness" \
    && git config user.email "harness@example.invalid" \
    && git commit --allow-empty -m "base source snapshot" \
    && git add src docs \
    && git commit -m "source snapshot"
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "incident_investigation_harness.app:app", "--host", "0.0.0.0", "--port", "8000"]
