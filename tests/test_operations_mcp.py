from __future__ import annotations

import asyncio
import uuid

import pytest

from incident_investigation_harness.mcp.operations_mcp import (
    mcp,
    query_operational_evidence,
    resolve_operational_evidence_citation,
)


def test_operations_mcp_contract_is_scoped_filterable_and_read_only() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "query_operational_evidence",
        "resolve_operational_evidence_citation",
    }

    result = query_operational_evidence(
        str(_id("incident-retry-storm")),
        str(_id("run-retry-storm-1")),
        evidence_types=["operational-metric"],
        operation="notification-processing",
    )
    assert result["logs"] == []
    assert {item["item"]["name"] for item in result["metrics"]} == {
        "notification.attempts.total",
        "notification.backlog",
        "notification.latency.p99",
    }
    assert {item["item"]["value"] for item in result["metrics"]} == {8, 16}
    assert all(
        item["citation"]["investigation_run_id"] == str(_id("run-retry-storm-1"))
        for item in result["metrics"]
    )

    complete = query_operational_evidence(
        str(_id("incident-retry-storm")),
        str(_id("run-retry-storm-1")),
    )
    assert complete["logs"][0]["item"]["values"]["status_code"] == 429
    assert {item["item"]["name"] for item in complete["metrics"]} >= {
        "notification.attempts.total",
        "notification.backlog",
        "notification.latency.p99",
    }
    assert complete["traces"][0]["item"]["values"] == {
        "attempts": 16,
        "backlog": 8,
        "p99": 16,
    }

    citation = result["metrics"][0]["citation"]
    assert resolve_operational_evidence_citation(**citation) is not None
    with pytest.raises(ValueError, match="operations-mcp"):
        resolve_operational_evidence_citation(
            provider="incident-mcp",
            incident_id=citation["incident_id"],
            investigation_run_id=citation["investigation_run_id"],
            evidence_type=citation["evidence_type"],
            evidence_id=citation["evidence_id"],
        )

    other = query_operational_evidence(
        str(_id("incident-healthy-reference")),
        str(_id("run-healthy-reference-1")),
    )
    assert other["metrics"] == []
    assert other["traces"] == []


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:{value}")
