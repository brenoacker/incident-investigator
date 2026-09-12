from __future__ import annotations

import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import psycopg

from incident_investigation_harness.adapters.knowledge_queries import (
    ALTER_DOCUMENTS_TABLE_SQL,
    CREATE_CITATION_SCOPES_TABLE_SQL,
    CREATE_DOCUMENTS_TABLE_SQL,
    CREATE_EMBEDDING_METADATA_TABLE_SQL,
    CREATE_EXTENSION_SQL,
    CREATE_PASSAGES_TABLE_SQL,
    DEAUTHORIZE_DOCUMENTS_SQL,
    DELETE_EMBEDDING_METADATA_SQL,
    HYBRID_QUERY_SQL,
    INSERT_CITATION_SCOPE_SQL,
    INSERT_EMBEDDING_METADATA_SQL,
    LEXICAL_QUERY_SQL,
    RESOLVE_CITATION_SQL,
    SELECT_EMBEDDING_METADATA_SQL,
    UPSERT_DOCUMENT_SQL,
    UPSERT_PASSAGE_SQL,
)
from incident_investigation_harness.knowledge_evidence import (
    CitedKnowledgePassage,
    EmbeddingProvider,
    KnowledgeDocument,
    KnowledgeEvidenceQuery,
    KnowledgeEvidenceResponse,
    KnowledgePassage,
    MatchKind,
)
from incident_investigation_harness.knowledge_indexing import (
    chunk_markdown,
    is_authorized_path,
    load_document,
    revision_id,
)


class PostgresKnowledgeEvidenceAdapter:  # pragma: no cover - exercised by PostgreSQL integration tests
    """Persistent, read-only query adapter for the synchronized knowledge index."""

    def __init__(self, database_url: str, embedding_provider: EmbeddingProvider, threshold: float = 0.12) -> None:
        self.database_url = database_url
        self.embedding_provider = embedding_provider
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        self.threshold = threshold
        if embedding_provider.dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")

    def initialize(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(CREATE_EXTENSION_SQL)
            connection.execute(CREATE_DOCUMENTS_TABLE_SQL)
            connection.execute(ALTER_DOCUMENTS_TABLE_SQL)
            connection.execute(
                CREATE_PASSAGES_TABLE_SQL.format(
                    dimensions=self.embedding_provider.dimensions
                )
            )
            connection.execute(CREATE_EMBEDDING_METADATA_TABLE_SQL)
            connection.execute(CREATE_CITATION_SCOPES_TABLE_SQL)
            connection.commit()

    def sync(self, root: Path, allowlist: frozenset[str]) -> int:
        if not all(is_authorized_path(path) for path in allowlist):
            raise ValueError("allowlist may only contain authorized knowledge documents")
        documents = tuple(load_document(root, path) for path in sorted(allowlist))
        self.initialize()
        written = 0
        with psycopg.connect(self.database_url) as connection:
            signature = (self.embedding_provider.name, self.embedding_provider.model, self.embedding_provider.model_revision, self.embedding_provider.dimensions)
            previous = connection.execute(SELECT_EMBEDDING_METADATA_SQL).fetchone()
            if previous and int(previous[3]) != self.embedding_provider.dimensions:
                raise ValueError(
                    "embedding dimensions changed; use a new knowledge index schema "
                    "before switching providers"
                )
            connection.execute(DELETE_EMBEDDING_METADATA_SQL)
            connection.execute(INSERT_EMBEDDING_METADATA_SQL, signature)
            connection.execute(DEAUTHORIZE_DOCUMENTS_SQL)
            for document in documents:
                current_revision_id = revision_id(document)
                passages = _passages(document)
                vectors = self.embedding_provider.embed([f"passage: {passage.text}" for passage in passages])
                connection.execute(
                    UPSERT_DOCUMENT_SQL,
                    (document.id, document.path, document.title, document.document_type, current_revision_id, self.embedding_provider.name, self.embedding_provider.model, self.embedding_provider.model_revision, self.embedding_provider.dimensions),
                )
                for passage, vector in zip(passages, vectors):
                    connection.execute(
                        UPSERT_PASSAGE_SQL,
                        (*_row(passage), _vector_literal(vector)),
                    )
                    written += 1
            connection.commit()
        return written

    def query(self, query: KnowledgeEvidenceQuery) -> KnowledgeEvidenceResponse:
        # Querying through a deterministic fake is intentionally not used here: this
        # adapter keeps the SQL boundary explicit and fails closed when unavailable.
        try:
            vector = self.embedding_provider.embed([f"query: {query.query or ''}"])[0]
        except (ImportError, RuntimeError):
            return self._query_lexical(query)
        vector_literal = _vector_literal(vector)
        types = tuple(query.document_types or ("runbook", "adr"))
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                HYBRID_QUERY_SQL,
                (query.query or "", vector_literal, query.query or "", vector_literal, list(types), self.threshold, query.limit),
            ).fetchall()
        response = _response_from_rows(query, rows)
        self._record_scopes(query, response)
        return response

    def _record_scopes(self, query: KnowledgeEvidenceQuery, response: KnowledgeEvidenceResponse) -> None:
        with psycopg.connect(self.database_url) as connection:
            for passage in response.passages:
                connection.execute(INSERT_CITATION_SCOPE_SQL, (passage.item.passage_id, query.context.incident_id, query.context.investigation_run_id))
            connection.commit()

    def _query_lexical(self, query: KnowledgeEvidenceQuery) -> KnowledgeEvidenceResponse:
        types = list(query.document_types or ("runbook", "adr"))
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                LEXICAL_QUERY_SQL,
                (query.query or "", types, query.query or "", self.threshold, query.limit),
            ).fetchall()
        response = _response_from_lexical_rows(query, rows)
        self._record_scopes(query, response)
        return response

    def resolve(self, citation: Any) -> CitedKnowledgePassage | None:
        if getattr(citation, "provider", None) != "knowledge-mcp" or getattr(citation, "evidence_type", None) != "knowledge-document":
            raise ValueError("citation must belong to knowledge-mcp")
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                RESOLVE_CITATION_SQL,
                (citation.evidence_id, citation.incident_id, citation.investigation_run_id),
            ).fetchone()
        if row is None:
            return None
        passage = KnowledgePassage(
            passage_id=row[0], document_id=row[1], revision_id=str(row[2]), path=row[3],
            title=row[4], document_type=row[5], text=row[6], ordinal=row[7],
        )
        return CitedKnowledgePassage(
            item=passage, relevance_score=1.0, match_kind="hybrid", citation=citation
        )


def _passages(document: KnowledgeDocument) -> tuple[KnowledgePassage, ...]:  # pragma: no cover - exercised by PostgreSQL integration tests
    revision = revision_id(document)
    return tuple(
        KnowledgePassage(
            passage_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{document.id}:{revision}:{ordinal}:{text}"),
            document_id=document.id, revision_id=revision, path=document.path, title=document.title,
            document_type=document.document_type, text=text, ordinal=ordinal,
        )
        for ordinal, text in enumerate(chunk_markdown(document.content, 600, 100))
    )


def _row(passage: KnowledgePassage) -> tuple[object, ...]:  # pragma: no cover - exercised by PostgreSQL integration tests
    return tuple(getattr(passage, field) for field in ("passage_id", "document_id", "revision_id", "path", "title", "document_type", "text", "ordinal"))


def _vector_literal(vector: Iterable[float]) -> str:  # pragma: no cover - exercised by PostgreSQL integration tests
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _response_from_rows(query: KnowledgeEvidenceQuery, rows: list[tuple[Any, ...]]) -> KnowledgeEvidenceResponse:  # pragma: no cover - exercised by PostgreSQL integration tests
    from incident_investigation_harness.evidence import EvidenceCitation
    context = query.context
    passages = []
    for row in rows:
        passage = KnowledgePassage(
            passage_id=cast(uuid.UUID, row[0]), document_id=cast(uuid.UUID, row[1]), revision_id=str(row[2]), path=str(row[3]), title=str(row[4]),
            document_type=cast(Any, row[5]), text=str(row[6]), ordinal=int(row[7]),
        )
        if context:
            citation = EvidenceCitation(provider="knowledge-mcp", incident_id=context.incident_id, investigation_run_id=context.investigation_run_id, evidence_type="knowledge-document", evidence_id=passage.passage_id)
        lexical_score = float(row[8])
        semantic_score = max(0.0, float(row[9]))
        kind = "hybrid" if lexical_score and semantic_score else "lexical" if lexical_score else "semantic"
        passages.append(CitedKnowledgePassage(item=passage, relevance_score=min(1.0, max(0.0, float(row[10]))), match_kind=cast(MatchKind, kind), citation=citation))
    return KnowledgeEvidenceResponse(context=context, passages=tuple(passages), retrieval_mode="hybrid")


def _response_from_lexical_rows(query: KnowledgeEvidenceQuery, rows: list[tuple[Any, ...]]) -> KnowledgeEvidenceResponse:  # pragma: no cover - exercised by PostgreSQL integration tests
    response_rows = [(*row, 0.0, float(row[8])) for row in rows]
    response = _response_from_rows(query, response_rows)
    return response.model_copy(update={"retrieval_mode": "lexical", "degraded": True, "degraded_reason": "semantic embedding provider unavailable"})
