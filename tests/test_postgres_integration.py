from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from incident_investigation_harness.app import app


@pytest.mark.integration
def test_ticket_survives_an_api_process_restart() -> None:
    if "DATABASE_URL" not in os.environ:
        pytest.skip("set DATABASE_URL to run the PostgreSQL integration test")

    created, fetched = asyncio.run(_create_then_restart_and_fetch())

    assert fetched.status_code == 200
    assert fetched.json() == created.json()


async def _create_then_restart_and_fetch() -> tuple[httpx.Response, httpx.Response]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as first_process:
            created = await first_process.post(
                "/tickets",
                json={
                    "title": "Ticket survives restart",
                    "description": "The ticket must remain available after the API restarts.",
                    "requester_email": "oncall@example.com",
                },
            )

    assert created.status_code == 201
    ticket_id = uuid.UUID(created.json()["id"])

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as restarted_process:
            fetched = await restarted_process.get(f"/tickets/{ticket_id}")

    return created, fetched
