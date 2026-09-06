from __future__ import annotations

import asyncio
import uuid

import pytest

from incident_investigation_harness.mcp.knowledge_mcp import (
    mcp,
    query_knowledge_evidence,
    resolve_knowledge_evidence_citation,
)


def test_knowledge_mcp_contract_is_allowlisted_cited_and_read_only() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "query_knowledge_evidence",
        "resolve_knowledge_evidence_citation",
    }

    result = query_knowledge_evidence(
        str(_id("incident-retry-storm")),
        str(_id("run-retry-storm-1")),
        query="429",
    )

    assert len(result["documents"]) == 1
    document = result["documents"][0]
    assert document["item"]["path"] == "docs/scenarios/retry-storm-latency.md"
    assert "429" in document["excerpt"]
    assert document["citation"]["provider"] == "knowledge-mcp"
    assert document["citation"]["investigation_run_id"] == str(_id("run-retry-storm-1"))
    assert resolve_knowledge_evidence_citation(**document["citation"]) is not None

    assert query_knowledge_evidence(
        str(_id("incident-retry-storm")),
        str(_id("run-retry-storm-1")),
        query="source-mcp",
    )["documents"] == []
    with pytest.raises(ValueError, match="knowledge-mcp"):
        resolve_knowledge_evidence_citation(
            provider="operations-mcp",
            incident_id=document["citation"]["incident_id"],
            investigation_run_id=document["citation"]["investigation_run_id"],
            evidence_type=document["citation"]["evidence_type"],
            evidence_id=document["citation"]["evidence_id"],
        )


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:{value}")
