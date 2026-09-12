from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from incident_investigation_harness.knowledge_evidence import (
    KnowledgeDocument,
    KnowledgeDocumentType,
)

_AUTHORIZED_PATH_PREFIXES = ("docs/adr/", "docs/runbooks/", "docs/scenarios/")


def is_authorized_path(path: str) -> bool:
    return path.startswith(_AUTHORIZED_PATH_PREFIXES)


def load_document(root: Path, relative_path: str) -> KnowledgeDocument:
    content = (root / relative_path).read_text(encoding="utf-8")
    document_type: KnowledgeDocumentType = "adr" if relative_path.startswith("docs/adr/") else "runbook"
    title = next((line.removeprefix("# ").strip() for line in content.splitlines() if line.startswith("# ")), relative_path)
    return KnowledgeDocument(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:knowledge:{relative_path}"),
        path=relative_path, title=title, content=content, document_type=document_type,
    )


def revision_id(document: KnowledgeDocument) -> str:
    return hashlib.sha256(document.content.encode("utf-8")).hexdigest()


def chunk_markdown(content: str, chunk_size: int = 600, overlap: int = 100) -> tuple[str, ...]:
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")
    heading = ""
    units: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            heading = line
        else:
            units.append(f"{heading}\n{line}" if heading else line)
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for unit in units:
        words = unit.split()
        while words:
            available = chunk_size - current_size
            if current and len(words) > available:
                chunks.append("\n".join(current))
                overlap_words = " ".join(current).split()[-overlap:]
                current = [" ".join(overlap_words)] if overlap_words else []
                current_size = len(overlap_words)
                continue
            take = min(len(words), available)
            current.append(" ".join(words[:take]))
            current_size += take
            words = words[take:]
            if current_size == chunk_size:
                chunks.append("\n".join(current))
                overlap_words = " ".join(current).split()[-overlap:]
                current = [" ".join(overlap_words)] if overlap_words else []
                current_size = len(overlap_words)
    if current:
        chunks.append("\n".join(current))
    return tuple(chunks)
