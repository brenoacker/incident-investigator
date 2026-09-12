"""SQL statements used by the PostgreSQL knowledge adapter."""

CREATE_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector"

CREATE_DOCUMENTS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        document_id UUID NOT NULL,
        path TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        document_type TEXT NOT NULL,
        current_revision_id CHAR(64) NOT NULL,
        provider_name TEXT NOT NULL,
        model_name TEXT NOT NULL,
        model_revision TEXT NOT NULL,
        embedding_dimensions INTEGER NOT NULL,
        authorized BOOLEAN NOT NULL DEFAULT TRUE
    )
"""

ALTER_DOCUMENTS_TABLE_SQL = """
    ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS provider_name TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS model_name TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS model_revision TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER NOT NULL DEFAULT 384
"""

CREATE_PASSAGES_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS knowledge_passages (
        passage_id UUID PRIMARY KEY,
        document_id UUID NOT NULL,
        revision_id CHAR(64) NOT NULL,
        path TEXT NOT NULL,
        title TEXT NOT NULL,
        document_type TEXT NOT NULL,
        passage_text TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        embedding vector({dimensions}) NOT NULL,
        UNIQUE (document_id, revision_id, ordinal)
    )
"""

CREATE_EMBEDDING_METADATA_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS knowledge_embedding_metadata (
        id BOOLEAN PRIMARY KEY DEFAULT TRUE,
        provider_name TEXT NOT NULL,
        model_name TEXT NOT NULL,
        model_revision TEXT NOT NULL,
        dimensions INTEGER NOT NULL
    )
"""

CREATE_CITATION_SCOPES_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS knowledge_citation_scopes (
        passage_id UUID NOT NULL,
        incident_id UUID NOT NULL,
        investigation_run_id UUID NOT NULL,
        PRIMARY KEY (passage_id, incident_id, investigation_run_id)
    )
"""

SELECT_EMBEDDING_METADATA_SQL = """
    SELECT provider_name, model_name, model_revision, dimensions
    FROM knowledge_embedding_metadata
    WHERE id = TRUE
"""

DELETE_EMBEDDING_METADATA_SQL = "DELETE FROM knowledge_embedding_metadata"

INSERT_EMBEDDING_METADATA_SQL = """
    INSERT INTO knowledge_embedding_metadata
        (provider_name, model_name, model_revision, dimensions)
    VALUES (%s, %s, %s, %s)
"""

DEAUTHORIZE_DOCUMENTS_SQL = "UPDATE knowledge_documents SET authorized = FALSE"

UPSERT_DOCUMENT_SQL = """
    INSERT INTO knowledge_documents
        (document_id, path, title, document_type, current_revision_id,
         provider_name, model_name, model_revision, embedding_dimensions, authorized)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
    ON CONFLICT (path) DO UPDATE SET
        title = EXCLUDED.title,
        document_type = EXCLUDED.document_type,
        current_revision_id = EXCLUDED.current_revision_id,
        provider_name = EXCLUDED.provider_name,
        model_name = EXCLUDED.model_name,
        model_revision = EXCLUDED.model_revision,
        embedding_dimensions = EXCLUDED.embedding_dimensions,
        authorized = TRUE
"""

UPSERT_PASSAGE_SQL = """
    INSERT INTO knowledge_passages
        (passage_id, document_id, revision_id, path, title, document_type,
         passage_text, ordinal, embedding)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (passage_id) DO UPDATE SET embedding = EXCLUDED.embedding
"""

HYBRID_QUERY_SQL = """
    WITH ranked AS (
    SELECT passage_id, document_id, revision_id, path, title, document_type,
           passage_text, ordinal,
           ts_rank_cd(to_tsvector('simple', passage_text), plainto_tsquery('simple', %s)) AS lexical_score,
           1 - (embedding <=> %s::vector) AS semantic_score,
           (ts_rank_cd(to_tsvector('simple', passage_text), plainto_tsquery('simple', %s))
            + GREATEST(1 - (embedding <=> %s::vector), 0)) / 2 AS relevance_score
    FROM knowledge_passages p
    JOIN knowledge_documents d USING (document_id)
    WHERE d.authorized AND d.current_revision_id = p.revision_id
      AND document_type = ANY(%s)
    )
    SELECT * FROM ranked
    WHERE relevance_score >= %s
    ORDER BY relevance_score DESC, document_id, revision_id, passage_id
    LIMIT %s
"""

INSERT_CITATION_SCOPE_SQL = """
    INSERT INTO knowledge_citation_scopes
        (passage_id, incident_id, investigation_run_id)
    VALUES (%s, %s, %s)
    ON CONFLICT DO NOTHING
"""

LEXICAL_QUERY_SQL = """
    SELECT passage_id, document_id, revision_id, path, title, document_type,
           passage_text, ordinal,
           ts_rank_cd(to_tsvector('simple', passage_text), plainto_tsquery('simple', %s)) AS lexical_score
    FROM knowledge_passages p JOIN knowledge_documents d USING (document_id)
    WHERE d.authorized AND d.current_revision_id = p.revision_id
      AND document_type = ANY(%s)
      AND ts_rank_cd(to_tsvector('simple', passage_text), plainto_tsquery('simple', %s)) >= %s
    ORDER BY lexical_score DESC, document_id, revision_id, passage_id LIMIT %s
"""

RESOLVE_CITATION_SQL = """
    SELECT passage_id, document_id, revision_id, path, title, document_type,
           passage_text, ordinal
    FROM knowledge_passages p JOIN knowledge_documents d USING (document_id)
    WHERE p.passage_id = %s AND d.authorized
      AND d.current_revision_id = p.revision_id
      AND EXISTS (
          SELECT 1 FROM knowledge_citation_scopes s
          WHERE s.passage_id = p.passage_id
            AND s.incident_id = %s
            AND s.investigation_run_id = %s
      )
"""
