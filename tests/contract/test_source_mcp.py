from __future__ import annotations

import asyncio
import uuid

import pytest

from incident_investigation_harness.mcp.source_mcp import (
    mcp,
    query_source_evidence,
    resolve_source_evidence_citation,
)


def test_source_mcp_exposes_only_read_only_tools() -> None:
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "query_source_evidence",
        "resolve_source_evidence_citation",
    }


def test_query_returns_allowlisted_source_artifacts() -> None:
    result = query_source_evidence(*_run_ids(), query="EvidenceCitation")

    assert result["artifacts"]
    assert all(
        artifact["item"]["path"].startswith("src/")
        for artifact in result["artifacts"]
    )
    assert all(
        artifact["citation"]["provider"] == "source-mcp"
        for artifact in result["artifacts"]
    )


def test_source_citation_resolves_and_arbitrary_path_is_denied() -> None:
    result = query_source_evidence(*_run_ids(), evidence_types=["source-code"])
    citation = result["artifacts"][0]["citation"]

    resolved = resolve_source_evidence_citation(**citation)
    assert resolved is not None
    assert resolved["citation"] == citation

    denied = query_source_evidence(
        *_run_ids(), paths=["docs/incident-oracle.md"]
    )
    assert denied["artifacts"] == []


def test_source_mcp_rejects_a_citation_from_another_provider() -> None:
    with pytest.raises(ValueError):
        resolve_source_evidence_citation(
            provider="knowledge-mcp",
            incident_id=_run_ids()[0],
            investigation_run_id=_run_ids()[1],
            evidence_type="source-code",
            evidence_id=str(uuid.uuid4()),
        )


def _run_ids() -> tuple[str, str]:
    return str(_id("incident")), str(_id("run"))


def _id(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:{value}")
