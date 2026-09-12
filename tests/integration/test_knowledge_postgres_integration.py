from __future__ import annotations

import os
import uuid

import pytest

from incident_investigation_harness.adapters.knowledge_evidence import (
    FakeEmbeddingProvider,
)
from incident_investigation_harness.adapters.postgres_knowledge import (
    PostgresKnowledgeEvidenceAdapter,
)
from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.knowledge_evidence import KnowledgeEvidenceQuery


@pytest.mark.integration
def test_postgres_index_sync_query_and_revision_citation(tmp_path) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("set DATABASE_URL to run the PostgreSQL knowledge integration test")
    document_path = tmp_path / "docs" / "runbooks" / "retry.md"
    document_path.parent.mkdir(parents=True)
    document_path.write_text("# Retry\nUse bounded backoff and jitter.", encoding="utf-8")
    relative_path = "docs/runbooks/retry.md"
    adapter = PostgresKnowledgeEvidenceAdapter(database_url, FakeEmbeddingProvider())
    allowlist = frozenset({relative_path})
    assert adapter.sync(tmp_path, allowlist) == 1

    context = InvestigationContext(incident_id=uuid.uuid4(), investigation_run_id=uuid.uuid4())
    result = adapter.query(KnowledgeEvidenceQuery(context=context, query="backoff"))

    assert result.passages[0].item.path == relative_path
    assert adapter.resolve(result.passages[0].citation) is not None

    document_path.write_text("# Retry\nUse bounded backoff, jitter and an attempt limit.", encoding="utf-8")
    adapter.sync(tmp_path, allowlist)
    changed = adapter.query(KnowledgeEvidenceQuery(context=context, query="attempt limit"))
    assert changed.passages[0].item.revision_id != result.passages[0].item.revision_id
