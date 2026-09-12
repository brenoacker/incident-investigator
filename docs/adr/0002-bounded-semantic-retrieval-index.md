# Bounded semantic retrieval with replaceable embedding adapters

The `knowledge-mcp` will evolve from whole-document lookup to bounded hybrid retrieval over an explicit PostgreSQL/pgvector index. The index is synchronized idempotently from the knowledge allowlist, preserves document revisions for citation resolution, and uses a replaceable `EmbeddingProvider`; the initial operational provider is the local `intfloat/multilingual-e5-small` model, while an OpenAI adapter remains optional for a future API-key-enabled environment. Generation and summarization remain outside the MCP, in the investigation coordinator.

## Consequences

- The investigator receives ranked, revision-specific passages as `Untrusted Evidence`, never generated answers.
- Allowlist enforcement applies during indexing, retrieval and citation resolution.
- Changing embedding provider, model or dimensions requires compatible reindexing.
- The local provider avoids requiring OpenAI API credentials for the initial implementation.
