from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.knowledge_evidence import (
    CitedKnowledgeDocument,
    KnowledgeDocument,
    KnowledgeDocumentType,
    KnowledgeEvidenceQuery,
    KnowledgeEvidenceResponse,
)

_AUTHORIZED_PATH_PREFIXES = ("docs/adr/", "docs/runbooks/", "docs/scenarios/")


@dataclass(frozen=True)
class KnowledgeEvidenceRepositoryFake:
    documents: tuple[KnowledgeDocument, ...]
    allowlist: frozenset[str]

    def query(self, query: KnowledgeEvidenceQuery) -> KnowledgeEvidenceResponse:
        search = query.query.casefold() if query.query else None
        documents = tuple(
            self._cite(document, query)
            for document in self.documents
            if _is_authorized_path(document.path)
            and document.path in self.allowlist
            and (
                query.document_types is None
                or document.document_type in query.document_types
            )
            and (
                search is None
                or search in f"{document.title}\n{document.content}".casefold()
            )
        )
        return KnowledgeEvidenceResponse(context=query.context, documents=documents)

    def resolve(self, citation: EvidenceCitation) -> CitedKnowledgeDocument | None:
        if (
            citation.provider != "knowledge-mcp"
            or citation.evidence_type != "knowledge-document"
        ):
            raise ValueError("citation must belong to knowledge-mcp")
        for document in self.documents:
            if (
                _is_authorized_path(document.path)
                and document.path in self.allowlist
                and document.id == citation.evidence_id
            ):
                return self._cite(
                    document,
                    KnowledgeEvidenceQuery(
                        context=InvestigationContext(
                            incident_id=citation.incident_id,
                            investigation_run_id=citation.investigation_run_id,
                        )
                    ),
                )
        return None

    @staticmethod
    def _cite(document: KnowledgeDocument, query: KnowledgeEvidenceQuery) -> CitedKnowledgeDocument:
        return CitedKnowledgeDocument(
            item=document,
            excerpt=_excerpt(document.content, query.query),
            citation=EvidenceCitation(
                provider="knowledge-mcp",
                incident_id=query.context.incident_id,
                investigation_run_id=query.context.investigation_run_id,
                evidence_type="knowledge-document",
                evidence_id=document.id,
            ),
        )


class KnowledgeEvidenceAdapter(KnowledgeEvidenceRepositoryFake):
    """Read-only filesystem adapter constrained to an explicit document allowlist."""

    @classmethod
    def from_allowlist(cls, root: Path, allowlist: frozenset[str]) -> KnowledgeEvidenceAdapter:
        if not all(_is_authorized_path(path) for path in allowlist):
            raise ValueError("allowlist may only contain authorized knowledge documents")
        documents = tuple(
            _load_document(root, relative_path)
            for relative_path in sorted(allowlist)
        )
        return cls(documents=documents, allowlist=allowlist)


def _load_document(root: Path, relative_path: str) -> KnowledgeDocument:
    path = root / relative_path
    content = path.read_text(encoding="utf-8")
    document_type: KnowledgeDocumentType = (
        "adr" if relative_path.startswith("docs/adr/") else "runbook"
    )
    return KnowledgeDocument(
        id=uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"incident-investigation-harness:knowledge:{relative_path}",
        ),
        path=relative_path,
        title=_title(content, relative_path),
        content=content,
        document_type=document_type,
    )


def _title(content: str, path: str) -> str:
    return next(
        (
            line.removeprefix("# ").strip()
            for line in content.splitlines()
            if line.startswith("# ")
        ),
        path,
    )


def _is_authorized_path(path: str) -> bool:
    return path.startswith(_AUTHORIZED_PATH_PREFIXES)


def _excerpt(content: str, query: str | None) -> str:
    if query is None:
        return content
    query_casefold = query.casefold()
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if query_casefold in line.casefold():
            start = max(0, index - 1)
            return "\n".join(lines[start : index + 2])
    return content
