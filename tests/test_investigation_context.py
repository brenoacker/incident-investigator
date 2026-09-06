from __future__ import annotations

import asyncio
import uuid

import httpx

from incident_investigation_harness.adapters.notification_provider import LocalNotificationProvider
from incident_investigation_harness.app import app
from incident_investigation_harness.notifications import NotificationWorker
from tests.fakes import NotificationQueueFake, NotificationRequestRepositoryFake, TicketRepositoryFake


def test_investigation_run_context_is_propagated_and_queryable() -> None:
    ticket_repository = TicketRepositoryFake()
    request_repository = NotificationRequestRepositoryFake()
    queue = NotificationQueueFake()
    app.state.ticket_repository = ticket_repository
    app.state.notification_request_repository = request_repository
    app.state.notification_queue = queue

    result = asyncio.run(_exercise_two_runs())

    assert result["tickets_first"] == 1
    assert result["tickets_second"] == 1
    assert result["requests_first"] == 1
    assert result["requests_second"] == 1
    assert result["request_context"] == result["ticket_context"]
    assert result["message_context"] == result["ticket_context"]
    assert result["attempt_context"] == result["ticket_context"]


def test_ticket_creation_rejects_missing_investigation_context() -> None:
    app.state.ticket_repository = TicketRepositoryFake()
    response = asyncio.run(_post({
        "title": "Missing context", "description": "Context is required",
        "requester_email": "oncall@example.com",
    }, "/tickets"))
    assert response.status_code == 422


async def _exercise_two_runs() -> dict[str, object]:
    first = _context(1)
    second = _context(2)
    created_first = await _post(_ticket_payload(first), "/tickets")
    created_second = await _post(_ticket_payload(second), "/tickets")
    request = await _post({}, f"/tickets/{created_first.json()['id']}/notifications")
    await _post({}, f"/tickets/{created_second.json()['id']}/notifications")
    message = app.state.notification_queue.pop()
    provider = LocalNotificationProvider()
    worker = NotificationWorker(app.state.notification_request_repository, app.state.notification_queue, provider)
    await worker.process(message)
    delivered = await _post({}, f"/notification-requests/{request.json()['id']}", method="GET")
    first_tickets = await _post({}, f"/tickets?investigation_run_id={first['investigation_run_id']}", method="GET")
    second_tickets = await _post({}, f"/tickets?investigation_run_id={second['investigation_run_id']}", method="GET")
    first_requests = await _post({}, f"/notification-requests?investigation_run_id={first['investigation_run_id']}", method="GET")
    second_requests = await _post({}, f"/notification-requests?investigation_run_id={second['investigation_run_id']}", method="GET")
    return {
        "tickets_first": len(first_tickets.json()), "tickets_second": len(second_tickets.json()),
        "requests_first": len(first_requests.json()), "requests_second": len(second_requests.json()),
        "ticket_context": created_first.json()["investigation_context"],
        "request_context": delivered.json()["investigation_context"],
        "message_context": message.investigation_context.model_dump(mode="json"),
        "attempt_context": provider.attempts[0].investigation_context.model_dump(mode="json"),
    }


def _context(number: int) -> dict[str, str]:
    return {"incident_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"incident-{number}")), "investigation_run_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"run-{number}"))}


def _ticket_payload(context: dict[str, str]) -> dict[str, object]:
    return {"title": "Contextual ticket", "description": "The run identity must survive processing.", "requester_email": "oncall@example.com", "investigation_context": context}


async def _post(payload: dict[str, object], path: str, method: str = "POST") -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        return await client.request(method, path, json=payload)
