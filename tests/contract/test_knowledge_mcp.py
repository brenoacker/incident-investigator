from __future__ import annotations

import asyncio
import uuid

import pytest

from incident_investigation_harness.mcp.knowledge_mcp import (
    mcp,
    query_knowledge_evidence,
    resolve_knowledge_evidence_citation,
)


def test_knowledge_mcp_exposes_only_read_only_tools() -> None:
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "query_knowledge_evidence",
        "resolve_knowledge_evidence_citation",
    }


def test_query_returns_an_authorized_runbook_or_adr() -> None:
    result = query_knowledge_evidence(*_run_ids(), query="429")

    assert len(result["passages"]) == 1
    assert (
        result["passages"][0]["item"]["path"]
        == "docs/scenarios/retry-storm-latency.md"
    )
    assert "429" in result["passages"][0]["item"]["text"]
    assert result["passages"][0]["is_untrusted"] is True


def test_query_scopes_citation_to_the_investigation_run() -> None:
    result = query_knowledge_evidence(*_run_ids(), query="429")
    citation = result["passages"][0]["citation"]

    assert citation["provider"] == "knowledge-mcp"
    assert citation["evidence_type"] == "knowledge-document"
    assert citation["investigation_run_id"] == str(_id("run-retry-storm-1"))


def test_resolve_returns_the_queried_document() -> None:
    result = query_knowledge_evidence(*_run_ids(), query="429")
    citation = result["passages"][0]["citation"]

    resolved = resolve_knowledge_evidence_citation(**citation)

    assert resolved is not None
    assert resolved["item"]["path"] == "docs/scenarios/retry-storm-latency.md"
    assert resolved["citation"] == citation


def test_resolve_rejects_a_citation_from_another_provider() -> None:
    result = query_knowledge_evidence(*_run_ids(), query="429")
    citation = result["passages"][0]["citation"]

    with pytest.raises(ValueError, match="knowledge-mcp"):
        resolve_knowledge_evidence_citation(
            provider="operations-mcp",
            incident_id=citation["incident_id"],
            investigation_run_id=citation["investigation_run_id"],
            evidence_type=citation["evidence_type"],
            evidence_id=citation["evidence_id"],
        )


def test_query_does_not_return_unmatched_content() -> None:
    result = query_knowledge_evidence(*_run_ids(), query="source-mcp")

    assert result["passages"] == []


def _run_ids() -> tuple[str, str]:
    return str(_id("incident-retry-storm")), str(_id("run-retry-storm-1"))


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:{value}")
