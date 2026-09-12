from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import Request, urlopen

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.knowledge_evidence import (
    CitedKnowledgePassage,
    EmbeddingProvider,
    KnowledgeDocument,
    KnowledgeEvidenceQuery,
    KnowledgeEvidenceResponse,
    KnowledgePassage,
    RetrievalMode,
)
from incident_investigation_harness.knowledge_indexing import (
    chunk_markdown,
    is_authorized_path,
    load_document,
    revision_id,
)

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


class FakeEmbeddingProvider:
    name = "fake"
    model = "deterministic-v1"
    model_revision = "1"
    dimensions = 64

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hashed_vector(text, self.dimensions) for text in texts]


class LocalEmbeddingAdapter:
    """Adapter for a local SentenceTransformers embedding model."""

    name = "sentence-transformers"
    model_revision = "1"

    def __init__(self, model: str = "intfloat/multilingual-e5-small") -> None:
        self.model = model
        self._encoder: object | None = None
        self.dimensions = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]  # noqa: I001
            except ImportError as error:
                raise RuntimeError(
                    "sentence-transformers is required for local semantic retrieval"
                ) from error
            self._encoder = SentenceTransformer(self.model)
            self.dimensions = int(self._encoder.get_sentence_embedding_dimension())  # type: ignore[union-attr]
        encoded = self._encoder.encode(texts, normalize_embeddings=True)  # type: ignore[union-attr]
        return [vector.tolist() for vector in encoded]


class OpenAIEmbeddingAdapter:
    """Optional API adapter; credentials are never required by the investigator."""

    name = "openai"
    model_revision = "1"

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small") -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.dimensions = 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        payload = json.dumps({"model": self.model, "input": texts}).encode()
        request = Request(
            "https://api.openai.com/v1/embeddings",
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            values = json.loads(response.read())
        return [item["embedding"] for item in sorted(values["data"], key=lambda item: item["index"])]


@dataclass(frozen=True)
class KnowledgeEvidenceIndex:
    documents: tuple[KnowledgeDocument, ...]
    allowlist: frozenset[str]
    embedding_provider: EmbeddingProvider = field(default_factory=FakeEmbeddingProvider)
    threshold: float = 0.12
    chunk_size: int = 600
    overlap: int = 100
    _passages: tuple[KnowledgePassage, ...] = field(init=False, repr=False)
    _vectors: list[list[float]] | None = field(init=False, repr=False)
    _issued_scopes: set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        passages = self._build_passages()
        object.__setattr__(self, "_passages", passages)
        try:
            vectors = self.embedding_provider.embed([f"passage: {p.text}" for p in passages])
        except (ImportError, RuntimeError):
            vectors = None
        object.__setattr__(self, "_vectors", vectors)
        object.__setattr__(self, "_issued_scopes", set())

    def query(self, query: KnowledgeEvidenceQuery) -> KnowledgeEvidenceResponse:
        mode: RetrievalMode
        candidates = [
            (passage, index)
            for index, passage in enumerate(self._passages)
            if passage.path in self.allowlist
            and (query.document_types is None or passage.document_type in query.document_types)
        ]
        if query.query is None:
            ranked = [(passage, 1.0, "lexical") for passage, _ in candidates]
            mode = "lexical"
        else:
            try:
                query_vector = self.embedding_provider.embed([f"query: {query.query}"])[0]
            except (ImportError, RuntimeError):
                query_vector = None
            ranked = []
            for passage, index in candidates:
                lexical = _lexical_score(query.query, passage.text)
                semantic = max(0.0, _cosine(query_vector, self._vectors[index])) if query_vector and self._vectors else 0.0
                score = (lexical + semantic) / 2 if query_vector else lexical
                if score >= self.threshold:
                    kind = "hybrid" if lexical and semantic else "lexical" if lexical else "semantic"
                    ranked.append((passage, score, kind))
            mode = "hybrid" if query_vector else "lexical"
        ranked.sort(key=lambda item: (-item[1], str(item[0].document_id), item[0].revision_id, str(item[0].passage_id)))
        response = KnowledgeEvidenceResponse(
            context=query.context,
            passages=tuple(
                self._cite(passage, score, kind, query.context)
                for passage, score, kind in ranked[: query.limit]
            ),
            retrieval_mode=mode,
            degraded=bool(query.query and query_vector is None),
            degraded_reason=("semantic embedding provider unavailable" if query.query and query_vector is None else None),
        )
        if query.context:
            self._issued_scopes.update(
                (
                    passage.item.passage_id,
                    query.context.incident_id,
                    query.context.investigation_run_id,
                )
                for passage in response.passages
            )
        return response

    def resolve(self, citation: EvidenceCitation) -> CitedKnowledgePassage | None:
        if citation.provider != "knowledge-mcp" or citation.evidence_type != "knowledge-document":
            raise ValueError("citation must belong to knowledge-mcp")
        scope = (citation.evidence_id, citation.incident_id, citation.investigation_run_id)
        if scope not in self._issued_scopes:
            return None
        for passage in self._passages:
            if passage.passage_id == citation.evidence_id and passage.path in self.allowlist:
                return self._cite(
                    passage,
                    1.0,
                    "hybrid",
                    InvestigationContext(
                        incident_id=citation.incident_id,
                        investigation_run_id=citation.investigation_run_id,
                    ),
                )
        return None

    def _build_passages(self) -> tuple[KnowledgePassage, ...]:
        passages: list[KnowledgePassage] = []
        for document in sorted(self.documents, key=lambda item: item.path):
            if not is_authorized_path(document.path) or document.path not in self.allowlist:
                continue
            revision = revision_id(document)
            for ordinal, text in enumerate(chunk_markdown(document.content, self.chunk_size, self.overlap)):
                passage_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{document.id}:{revision}:{ordinal}:{text}",
                )
                passages.append(
                    KnowledgePassage(
                        passage_id=passage_id,
                        document_id=document.id,
                        revision_id=revision,
                        path=document.path,
                        title=document.title,
                        document_type=document.document_type,
                        text=text,
                        ordinal=ordinal,
                    )
                )
        return tuple(passages)

    @staticmethod
    def _cite(
        passage: KnowledgePassage,
        score: float,
        kind: str,
        context: InvestigationContext,
    ) -> CitedKnowledgePassage:
        return CitedKnowledgePassage(
            item=passage,
            relevance_score=min(1.0, max(0.0, score)),
            match_kind=kind,  # type: ignore[arg-type]
            citation=EvidenceCitation(
                provider="knowledge-mcp",
                incident_id=context.incident_id,
                investigation_run_id=context.investigation_run_id,
                evidence_type="knowledge-document",
                evidence_id=passage.passage_id,
            ),
        )


@dataclass(frozen=True)
class KnowledgeEvidenceRepositoryFake(KnowledgeEvidenceIndex):
    """Deterministic substitute for the knowledge evidence port."""


class KnowledgeEvidenceAdapter(KnowledgeEvidenceIndex):
    """Read-only filesystem adapter constrained to an explicit document allowlist."""

    @classmethod
    def from_allowlist(
        cls,
        root: Path,
        allowlist: frozenset[str],
        embedding_provider: EmbeddingProvider | None = None,
    ) -> KnowledgeEvidenceAdapter:
        if not all(is_authorized_path(path) for path in allowlist):
            raise ValueError("allowlist may only contain authorized knowledge documents")
        documents = tuple(load_document(root, path) for path in sorted(allowlist))
        return cls(
            documents=documents,
            allowlist=allowlist,
            embedding_provider=embedding_provider or FakeEmbeddingProvider(),
        )


def _lexical_score(query: str, text: str) -> float:
    query_terms = set(_TOKEN_RE.findall(query.casefold()))
    text_terms = set(_TOKEN_RE.findall(text.casefold()))
    return len(query_terms & text_terms) / len(query_terms) if query_terms else 0.0


def _hashed_vector(text: str, dimensions: int) -> list[float]:
    values = [0.0] * dimensions
    for token in _TOKEN_RE.findall(text.casefold()):
        digest = hashlib.sha256(token.encode()).digest()
        values[int.from_bytes(digest[:4], "big") % dimensions] += 1.0
    length = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / length for value in values]


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
