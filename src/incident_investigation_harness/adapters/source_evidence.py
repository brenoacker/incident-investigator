from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.evidence import EvidenceCitation
from incident_investigation_harness.source_evidence import (
    CitedSourceArtifact,
    SourceArtifact,
    SourceEvidenceQuery,
    SourceEvidenceRepository,
    SourceEvidenceResponse,
    SourceEvidenceType,
)


@dataclass(frozen=True)
class SourceEvidenceRepositoryFake(SourceEvidenceRepository):
    artifacts: tuple[SourceArtifact, ...]
    paths: frozenset[str]
    refs: frozenset[str]

    def query(self, query: SourceEvidenceQuery) -> SourceEvidenceResponse:
        search = query.query.casefold() if query.query else None
        artifacts = tuple(
            self._cite(artifact, query)
            for artifact in self.artifacts
            if artifact.path in self.paths
            and artifact.revision in self.refs
            and (query.paths is None or artifact.path in query.paths)
            and (query.refs is None or artifact.revision in query.refs)
            and (
                query.evidence_types is None
                or artifact.artifact_type in query.evidence_types
            )
            and (
                search is None
                or search in f"{artifact.path}\n{artifact.content}".casefold()
            )
        )
        return SourceEvidenceResponse(context=query.context, artifacts=artifacts)

    def resolve(self, citation: EvidenceCitation) -> CitedSourceArtifact | None:
        if citation.provider != "source-mcp":
            raise ValueError("citation must belong to source-mcp")
        for artifact in self.artifacts:
            if (
                artifact.id == citation.evidence_id
                and artifact.path in self.paths
                and artifact.revision in self.refs
                and artifact.artifact_type == citation.evidence_type
            ):
                return self._cite(
                    artifact,
                    SourceEvidenceQuery(
                        context=query_context(citation),
                    ),
                )
        return None

    @staticmethod
    def _cite(
        artifact: SourceArtifact, query: SourceEvidenceQuery
    ) -> CitedSourceArtifact:
        return CitedSourceArtifact(
            item=artifact,
            excerpt=_excerpt(artifact.content, query.query),
            citation=EvidenceCitation(
                provider="source-mcp",
                incident_id=query.context.incident_id,
                investigation_run_id=query.context.investigation_run_id,
                evidence_type=artifact.artifact_type,
                evidence_id=artifact.id,
            ),
        )


class SourceEvidenceAdapter(SourceEvidenceRepositoryFake):
    """Read-only Git adapter restricted to explicitly allowlisted paths and refs."""

    @classmethod
    def from_allowlist(
        cls, root: Path, paths: frozenset[str], refs: frozenset[str]
    ) -> SourceEvidenceAdapter:
        if not paths or not refs or not all(_is_allowed_path(path) for path in paths):
            raise ValueError("source allowlist contains an unauthorized path")
        if not all(_is_allowed_ref(ref) for ref in refs):
            raise ValueError("source allowlist contains an unauthorized ref")

        artifacts: list[SourceArtifact] = []
        for path in sorted(paths):
            for ref in sorted(refs):
                content = _source_content(root, ref, path)
                artifacts.append(
                    _artifact("source-code", path, ref, content)
                )
                history = _git(root, "log", "--format=%H %s", ref, "--", path)
                artifacts.append(_artifact("git-history", path, ref, history))
                diff = _git(root, "diff", f"{ref}^", ref, "--", path)
                artifacts.append(_artifact("source-diff", path, ref, diff or "No changes."))
        return cls(artifacts=tuple(artifacts), paths=paths, refs=refs)


def query_context(citation: EvidenceCitation) -> InvestigationContext:
    return InvestigationContext(
        incident_id=citation.incident_id,
        investigation_run_id=citation.investigation_run_id,
    )


def _artifact(
    artifact_type: str, path: str, revision: str, content: str
) -> SourceArtifact:
    return SourceArtifact(
        id=uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"incident-investigation-harness:source:{artifact_type}:{revision}:{path}",
        ),
        artifact_type=cast(SourceEvidenceType, artifact_type),
        path=path,
        revision=revision,
        content=content,
    )


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _source_content(root: Path, ref: str, relative_path: str) -> str:
    working_tree_path = root / relative_path
    if ref == "HEAD" and working_tree_path.is_file():
        return working_tree_path.read_text(encoding="utf-8")
    return _git(root, "show", f"{ref}:{relative_path}")


def _is_allowed_path(path: str) -> bool:
    return (
        path.startswith("src/")
        and not Path(path).is_absolute()
        and ".." not in Path(path).parts
        and ".git" not in Path(path).parts
    )


def _is_allowed_ref(ref: str) -> bool:
    return (
        bool(ref)
        and not ref.startswith("-")
        and all(character not in ref for character in "\r\n;|&")
    )


def _excerpt(content: str, query: str | None) -> str:
    if not content:
        return "No content."
    if query is None:
        return content
    query_casefold = query.casefold()
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if query_casefold in line.casefold():
            return "\n".join(lines[max(0, index - 1) : index + 2])
    return content
