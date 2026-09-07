import asyncio

import httpx
import pytest

from incident_investigation_harness.app import app


def test_health_reports_ready() -> None:
    response = asyncio.run(_request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def _request_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/health")


def test_lifespan_initializes_runtime_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRepository:
        def __init__(self, _url: str) -> None:
            self.initialized = False

        def initialize(self) -> None:
            self.initialized = True

    class FakeQueue:
        def __init__(self, url: str) -> None:
            self.url = url

    monkeypatch.setattr("incident_investigation_harness.app.PostgresTicketRepository", FakeRepository)
    monkeypatch.setattr(
        "incident_investigation_harness.app.PostgresNotificationRequestRepository",
        FakeRepository,
    )
    monkeypatch.setattr("incident_investigation_harness.app.RedisNotificationQueue", FakeQueue)

    asyncio.run(_exercise_lifespan())


async def _exercise_lifespan() -> None:
    async with app.router.lifespan_context(app):
        assert app.state.ticket_repository.initialized
        assert app.state.notification_request_repository.initialized
        assert app.state.notification_queue.url == "redis://redis:6379/0"
