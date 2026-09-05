from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from incident_investigation_harness.app import app
from incident_investigation_harness.adapters.notification_provider import (
    LocalNotificationProvider,
    ProviderFaultProfile,
)
from incident_investigation_harness.notifications import (
    NotificationMessage,
    NotificationStatus,
    NotificationWorker,
)
from tests.fakes import (
    InMemoryNotificationQueue,
    InMemoryNotificationRequestRepository,
    InMemoryTicketRepository,
)


def test_existing_ticket_creates_persisted_notification_request_and_queue_message() -> None:
    ticket_repository = InMemoryTicketRepository()
    notification_repository = InMemoryNotificationRequestRepository()
    queue = InMemoryNotificationQueue()
    app.state.ticket_repository = ticket_repository
    app.state.notification_request_repository = notification_repository
    app.state.notification_queue = queue

    created, requested, fetched, message = asyncio.run(
        _create_ticket_and_request_notification()
    )

    assert created.status_code == 201
    assert requested.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json() == requested.json()
    assert fetched.json()["status"] == "pending"
    assert message is not None
    assert message.request_id == uuid.UUID(requested.json()["id"])
    assert message.ticket_id == uuid.UUID(created.json()["id"])


def test_missing_ticket_does_not_create_or_publish_notification_request() -> None:
    app.state.ticket_repository = InMemoryTicketRepository()
    app.state.notification_request_repository = InMemoryNotificationRequestRepository()
    app.state.notification_queue = InMemoryNotificationQueue()
    missing_ticket_id = uuid.uuid4()

    response, message = asyncio.run(_request_for_missing_ticket(missing_ticket_id))

    assert response.status_code == 404
    assert message is None


def test_worker_delivers_request_and_reprocessing_does_not_duplicate_delivery() -> None:
    ticket_repository = InMemoryTicketRepository()
    notification_repository = InMemoryNotificationRequestRepository()
    queue = InMemoryNotificationQueue()
    provider = LocalNotificationProvider()
    app.state.ticket_repository = ticket_repository
    app.state.notification_request_repository = notification_repository
    app.state.notification_queue = queue

    created, requested, _, message = asyncio.run(
        _create_ticket_and_request_notification()
    )
    assert created.status_code == 201
    assert requested.status_code == 201
    assert message is not None

    worker = NotificationWorker(notification_repository, queue, provider)
    asyncio.run(worker.process_next())
    asyncio.run(worker.process(message))

    delivered = asyncio.run(_get_notification_request(requested.json()["id"]))

    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["delivery_result"] == "accepted"
    assert delivered.json()["delivered_at"] is not None
    assert len(provider.deliveries) == 1


def test_worker_does_not_mark_rate_limited_request_as_delivered() -> None:
    ticket_repository = InMemoryTicketRepository()
    notification_repository = InMemoryNotificationRequestRepository()
    queue = InMemoryNotificationQueue()
    provider = LocalNotificationProvider()
    provider.configure_fault_profile(ProviderFaultProfile(rate_limit_attempts=1))
    app.state.ticket_repository = ticket_repository
    app.state.notification_request_repository = notification_repository
    app.state.notification_queue = queue

    created, requested, _, message = asyncio.run(
        _create_ticket_and_request_notification()
    )
    assert created.status_code == 201
    assert requested.status_code == 201
    assert message is not None

    worker = NotificationWorker(notification_repository, queue, provider)
    asyncio.run(worker.process(message))

    pending = asyncio.run(_get_notification_request(requested.json()["id"]))

    assert pending.status_code == 200
    assert pending.json()["status"] == NotificationStatus.PENDING
    assert pending.json()["delivery_result"] is None
    assert pending.json()["delivered_at"] is None


def test_worker_stops_when_stop_requested() -> None:
    stop_event = asyncio.Event()
    stop_event.set()
    worker = NotificationWorker(
        InMemoryNotificationRequestRepository(),
        InMemoryNotificationQueue(),
        LocalNotificationProvider(),
    )

    asyncio.run(worker.run_forever(poll_interval=0, stop_event=stop_event))


@pytest.mark.integration
def test_notification_request_persists_and_reaches_redis_queue() -> None:
    if "DATABASE_URL" not in os.environ or "REDIS_URL" not in os.environ:
        pytest.skip("set DATABASE_URL and REDIS_URL to run the integration test")

    created, requested, fetched, message = asyncio.run(
        _create_notification_with_real_adapters()
    )

    assert created.status_code == 201
    assert requested.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json() == requested.json()
    assert message is not None
    assert message.request_id == uuid.UUID(requested.json()["id"])
    assert message.ticket_id == uuid.UUID(created.json()["id"])


@pytest.mark.integration
def test_worker_delivers_notification_with_real_adapters() -> None:
    if "DATABASE_URL" not in os.environ or "REDIS_URL" not in os.environ:
        pytest.skip("set DATABASE_URL and REDIS_URL to run the integration test")

    delivered = asyncio.run(_deliver_notification_with_real_adapters())

    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["delivery_result"] == "accepted"
    assert delivered.json()["delivered_at"] is not None


async def _create_ticket_and_request_notification() -> tuple[
    httpx.Response,
    httpx.Response,
    httpx.Response,
    NotificationMessage | None,
]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/tickets",
            json={
                "title": "Notification delivery is delayed",
                "description": "The incident timeline shows increasing delivery latency.",
                "requester_email": "oncall@example.com",
            },
        )
        requested = await client.post(f"/tickets/{created.json()['id']}/notifications")
        fetched = await client.get(
            f"/notification-requests/{requested.json()['id']}"
        )
    return created, requested, fetched, app.state.notification_queue.pop()


async def _request_for_missing_ticket(
    ticket_id: uuid.UUID,
) -> tuple[httpx.Response, NotificationMessage | None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/tickets/{ticket_id}/notifications")
    return response, app.state.notification_queue.pop()


async def _get_notification_request(request_id: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(f"/notification-requests/{request_id}")


async def _create_notification_with_real_adapters() -> tuple[
    httpx.Response,
    httpx.Response,
    httpx.Response,
    NotificationMessage | None,
]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            created = await client.post(
                "/tickets",
                json={
                    "title": "Notification persistence integration",
                    "description": "The request must be persisted and queued.",
                    "requester_email": "oncall@example.com",
                },
            )
            requested = await client.post(
                f"/tickets/{created.json()['id']}/notifications"
            )
            fetched = await client.get(
                f"/notification-requests/{requested.json()['id']}"
            )
        message = app.state.notification_queue.pop()
    return created, requested, fetched, message


async def _deliver_notification_with_real_adapters() -> tuple[
    httpx.Response
]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            created = await client.post(
                "/tickets",
                json={
                    "title": "Notification worker integration",
                    "description": "The worker must persist the delivery result.",
                    "requester_email": "oncall@example.com",
                },
            )
            requested = await client.post(
                f"/tickets/{created.json()['id']}/notifications"
            )
            worker = NotificationWorker(
                app.state.notification_request_repository,
                app.state.notification_queue,
                LocalNotificationProvider(),
            )
            await worker.process_next()
            delivered = await client.get(
                f"/notification-requests/{requested.json()['id']}"
            )
    return delivered
