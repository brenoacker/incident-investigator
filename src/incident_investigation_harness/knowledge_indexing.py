from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from incident_investigation_harness.knowledge_evidence import (
    KnowledgeDocument,
    KnowledgeDocumentType,
)

_AUTHORIZED_PATH_PREFIXES = ("docs/adr/", "docs/runbooks/", "docs/scenarios/")


def is_authorized_path(path: str) -> bool:
    candidate = Path(path)
    return (
        not candidate.is_absolute()
        and ".." not in candidate.parts
        and path.startswith(_AUTHORIZED_PATH_PREFIXES)
    )


def load_document(root: Path, relative_path: str) -> KnowledgeDocument:
    content = (root / relative_path).read_text(encoding="utf-8")
    document_type: KnowledgeDocumentType = "adr" if relative_path.startswith("docs/adr/") else "runbook"
    title = next((line.removeprefix("# ").strip() for line in content.splitlines() if line.startswith("# ")), relative_path)
    return KnowledgeDocument(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"incident-investigation-harness:knowledge:{relative_path}"),
        path=relative_path, title=title, content=content, document_type=document_type,
    )


def revision_id(document: KnowledgeDocument) -> str:
    return hashlib.sha256(normalize_content(document.content).encode("utf-8")).hexdigest()


def normalize_content(content: str) -> str:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


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
    tokens = re.findall(r"\w+|[^\w\s]", " ".join(units), re.UNICODE)
    step = chunk_size - overlap
    return tuple(
        _detokenize(tokens[start : start + chunk_size])
        for start in range(0, len(tokens), step)
    )


def _detokenize(tokens: list[str]) -> str:
    text = " ".join(tokens)
    return re.sub(r"\s+([.,!?;:)\]])", r"\1", text)
