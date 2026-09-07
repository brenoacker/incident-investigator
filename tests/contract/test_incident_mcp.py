from __future__ import annotations

import asyncio
import json
import uuid

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from incident_investigation_harness.mcp.incident_mcp import (
    mcp,
    query_incident_evidence,
    resolve_evidence_citation,
)


def test_incident_mcp_exposes_only_read_only_evidence_tools() -> None:
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "query_incident_evidence",
        "resolve_evidence_citation",
    }


def test_incident_mcp_returns_scoped_citations_and_resolves_them() -> None:
    result = query_incident_evidence(
        str(_id("incident-retry-storm")),
        str(_id("run-retry-storm-1")),
    )

    assert result["ticket"] is not None
    assert len(result["comments"]) == 1
    assert len(result["timeline"]) == 1
    assert all(
        item["citation"]["investigation_run_id"] == str(_id("run-retry-storm-1"))
        for item in [result["ticket"], *result["comments"], *result["timeline"]]
    )

    ticket_citation = result["ticket"]["citation"]
    resolved = resolve_evidence_citation(**ticket_citation)
    assert resolved is not None
    assert resolved["citation"] == ticket_citation

    other = query_incident_evidence(
        str(_id("incident-healthy-reference")),
        str(_id("run-healthy-reference-1")),
    )
    assert other["ticket"]["item"]["title"] == "Notification delivery healthy"
    assert other["comments"][0]["item"]["id"] != result["comments"][0]["item"]["id"]


def test_incident_mcp_rejects_invalid_citation_provider() -> None:
    try:
        resolve_evidence_citation(
            "other-provider",
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "ticket",
            "00000000-0000-0000-0000-000000000003",
        )
    except ValueError as error:
        assert "provider" in str(error)
    else:
        raise AssertionError("invalid provider should be rejected")


def test_incident_mcp_streamable_http_endpoint_serves_the_tools() -> None:
    result = asyncio.run(_query_over_streamable_http())

    assert result["ticket"]["item"]["title"] == "Notification delivery degraded"
    assert len(result["comments"]) == 1
    assert len(result["timeline"]) == 1


async def _query_over_streamable_http() -> dict[str, object]:
    app = mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            async with streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert {tool.name for tool in tools.tools} == {
                        "query_incident_evidence",
                        "resolve_evidence_citation",
                    }
                    response = await session.call_tool(
                        "query_incident_evidence",
                        {
                            "incident_id": str(_id("incident-retry-storm")),
                            "investigation_run_id": str(_id("run-retry-storm-1")),
                        },
                    )

    content = response.content[0]
    assert content.type == "text"
    return json.loads(content.text)


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:{value}")
