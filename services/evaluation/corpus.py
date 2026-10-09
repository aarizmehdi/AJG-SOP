"""Benchmark corpus: verified Markdown SOPs parsed through the production ingestion path.

The corpus is built with the same ``FixtureDocumentParser`` and ``Canonicalizer`` the product
uses, so the benchmark sees exactly the sections the product would index. Two deliberate
differences keep results reproducible and chunker-independent:

* Section ids are rewritten to deterministic values (the canonicalizer generates random ones).
* Every section gets a stable, human-readable *section key* (``d1:loading``) that benchmark cases
  reference. Chunk ids change with the chunker; section keys do not.

Access labels do not exist in the source Markdown. An explicit, clearly synthetic overlay file
assigns restrictions to some sections so authorization behaviour can be measured. The overlay is
an evaluation fixture only; it never touches production access data.
"""

import asyncio
import fnmatch
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from packages.contracts.access import (
    UNRESTRICTED_SCOPE,
    AccessDimension,
    AccessMode,
    AccessScope,
    EmployeeScope,
)
from packages.contracts.canonical import CanonicalSOP
from packages.contracts.source import SourceDocument, SourceFormat
from services.evaluation.metrics import normalize_text
from services.evaluation.models import EvaluationScope
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.structure.canonical_document import Canonicalizer

ORGANIZATION_ID = "ajg-eval"


class OverlayRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keys: list[str]
    departments: list[str] = []
    locations: list[str] = []
    roles: list[str] = []
    reason: str = ""


class AccessOverlay(BaseModel):
    """First matching rule wins. Empty dimension = unrestricted on that dimension."""

    model_config = ConfigDict(extra="forbid")
    note: str = ""
    rules: list[OverlayRule] = []


@dataclass(frozen=True)
class CorpusSection:
    key: str
    section_id: str
    document_tag: str
    heading_path: tuple[str, ...]
    policy_number: str | None
    text: str
    normalized_text: str
    access: AccessScope


@dataclass
class Corpus:
    organization_id: str
    documents: list[CanonicalSOP]
    sections: dict[str, CorpusSection]
    key_by_section_id: dict[str, str] = field(default_factory=dict)
    fingerprint: str = ""

    def allows(self, key: str, scope: EvaluationScope) -> bool:
        """Independent authorization oracle used to detect leaks (not the production filter)."""
        return self.sections[key].access.allows(
            EmployeeScope(
                organization_id=self.organization_id,
                departments=frozenset({scope.department}),
                locations=frozenset({scope.location}),
                organizational_roles=frozenset({scope.role}),
            )
        )

    def restricted_for(self, scope: EvaluationScope) -> set[str]:
        return {key for key in self.sections if not self.allows(key, scope)}


def _slug(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return slug[:limit].strip("-") or "section"


def document_tag(path: Path, ordinal: int) -> str:
    match = re.search(r"(\d+)\D*$", path.stem)
    return f"d{match.group(1)}" if match else f"d{ordinal}"


def section_key(tag: str, heading_path: tuple[str, ...], seen: dict[str, int]) -> str:
    parts = heading_path[1:] if len(heading_path) > 1 else heading_path
    base = f"{tag}:" + "/".join(_slug(part) for part in parts[-3:])
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}~{seen[base]}"


def _scope_for(rule: OverlayRule) -> AccessScope:
    def dimension(values: list[str]) -> AccessDimension:
        if not values:
            return AccessDimension(mode=AccessMode.ALL)
        return AccessDimension(mode=AccessMode.SELECTED, values=frozenset(values))

    return AccessScope(
        departments=dimension(rule.departments),
        locations=dimension(rule.locations),
        roles=dimension(rule.roles),
    )


def load_overlay(path: Path | None) -> AccessOverlay:
    if path is None or not path.exists():
        return AccessOverlay()
    return AccessOverlay.model_validate_json(path.read_text(encoding="utf-8"))


def _markdown_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.md"))


async def load_corpus_async(directory: Path, overlay: AccessOverlay | None = None) -> Corpus:
    files = _markdown_files(directory)
    if not files:
        raise FileNotFoundError(f"No Markdown SOP files found in {directory}")
    overlay = overlay or AccessOverlay()
    parser = FixtureDocumentParser()
    documents: list[CanonicalSOP] = []
    sections: dict[str, CorpusSection] = {}
    key_by_id: dict[str, str] = {}
    used_rules: set[int] = set()
    digest = hashlib.sha256()
    used_tags: set[str] = set()
    for ordinal, path in enumerate(files, start=1):
        tag = document_tag(path, ordinal)
        if tag in used_tags:
            raise ValueError(f"Duplicate document tag {tag!r}; rename {path.name}")
        used_tags.add(tag)
        content = path.read_bytes()
        digest.update(content)
        source = SourceDocument(
            id=f"source-{tag}",
            organization_id=ORGANIZATION_ID,
            policy_id=f"policy-{tag}",
            version_id=f"version-{tag}",
            file_name=path.name,
            media_type="text/markdown",
            source_format=SourceFormat.MARKDOWN,
            sha256=hashlib.sha256(content).hexdigest(),
            original_artifact_uri=f"eval://{path.name}",
        )
        raw = await parser.parse(source, content)
        canonical = Canonicalizer().canonicalize(source, raw)
        seen: dict[str, int] = {}
        id_map: dict[str, str] = {}
        keys: list[str] = []
        for index, section in enumerate(canonical.sections):
            id_map[section.id] = f"sec-{tag}-{index:03d}"
            keys.append(section_key(tag, section.heading_path, seen))
        rebuilt = []
        for section, key in zip(canonical.sections, keys, strict=True):
            access = UNRESTRICTED_SCOPE
            for rule_index, rule in enumerate(overlay.rules):
                if any(fnmatch.fnmatchcase(key, pattern) for pattern in rule.keys):
                    access = _scope_for(rule)
                    used_rules.add(rule_index)
                    break
            new_id = id_map[section.id]
            updated = section.model_copy(
                update={
                    "id": new_id,
                    "parent_section_id": id_map.get(section.parent_section_id or ""),
                    "access": access,
                }
            )
            rebuilt.append(updated)
            text = "\n".join(
                [
                    " > ".join(section.heading_path),
                    *(Canonicalizer.block_text(block) for block in section.blocks),
                ]
            )
            sections[key] = CorpusSection(
                key=key,
                section_id=new_id,
                document_tag=tag,
                heading_path=section.heading_path,
                policy_number=section.policy_number,
                text=text,
                normalized_text=normalize_text(text),
                access=access,
            )
            key_by_id[new_id] = key
        documents.append(
            canonical.model_copy(update={"id": f"canonical-{tag}", "sections": rebuilt})
        )
    unused = [overlay.rules[i].keys for i in range(len(overlay.rules)) if i not in used_rules]
    if unused:
        raise ValueError(f"Access overlay rules matched no section: {unused}")
    return Corpus(
        organization_id=ORGANIZATION_ID,
        documents=documents,
        sections=sections,
        key_by_section_id=key_by_id,
        fingerprint=digest.hexdigest()[:16],
    )


def load_corpus(directory: Path, overlay: AccessOverlay | None = None) -> Corpus:
    """Synchronous wrapper; use ``load_corpus_async`` from inside a running event loop."""
    return asyncio.run(load_corpus_async(directory, overlay))
