from __future__ import annotations

import argparse
import os
from pathlib import Path

from incident_investigation_harness.adapters.knowledge_evidence import (
    LocalEmbeddingAdapter,
)
from incident_investigation_harness.adapters.postgres_knowledge import (
    PostgresKnowledgeEvidenceAdapter,
)


def main() -> None:  # pragma: no cover - exercised by the operator CLI
    parser = argparse.ArgumentParser(description="Synchronize the bounded knowledge index")
    parser.add_argument("command", choices=("sync",))
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    allowlist = frozenset({
        "docs/scenarios/retry-storm-latency.md",
        "docs/adr/0001-postgresql-for-ticket-persistence.md",
    })
    adapter = PostgresKnowledgeEvidenceAdapter(
        os.environ.get("DATABASE_URL", "postgresql://ticketing:ticketing@db:5432/ticketing"),
        LocalEmbeddingAdapter(os.environ.get("KNOWLEDGE_EMBEDDING_MODEL", "intfloat/multilingual-e5-small")),
    )
    print(f"indexed passages: {adapter.sync(args.root, allowlist)}")


if __name__ == "__main__":
    main()
