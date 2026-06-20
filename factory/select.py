"""Select vault concept notes to turn into short-form videos.

Stdlib only. Concept notes live at DEFAULT_CONCEPTS_DIR as `*.md` files with a
tiny YAML frontmatter block followed by markdown sections. We do not depend on
pyyaml; the frontmatter values we care about are single-line scalars.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONCEPTS_DIR = Path("C:/Users/P/Project/lifeos/wiki/concepts")

# Order used when prefer_confidence sorting (high first).
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}

# Minimum words a Definition needs before it's worth scripting from.
_MIN_DEFINITION_WORDS = 12

# Split a doc into `## Section` chunks. Group 1 = heading text, group 2 = body.
_SECTION_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)


@dataclass
class Concept:
    slug: str
    path: Path
    title: str
    confidence: str
    domain: str
    source_count: int
    definition: str
    evidence: list[str] = field(default_factory=list)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Pull the leading `---`-delimited block into a flat {key: raw_value} dict.

    # ponytail: naive frontmatter parse — values are single-line scalars or `[]`
    lists in this vault, so a line split is enough; we never need nested YAML.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    out: dict[str, str] = {}
    for line in block.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out


def _split_sections(body: str) -> dict[str, str]:
    """Map `## Heading` -> text up to the next `##` (or EOF)."""
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[m.group(1).strip()] = body[start:end].strip()
    return sections


def _bullets(section: str) -> list[str]:
    """Return non-empty `-`/`*` bullet lines (marker stripped)."""
    out = []
    for line in section.splitlines():
        line = line.strip()
        if line[:1] in ("-", "*"):
            item = line[1:].strip()
            if item:
                out.append(item)
    return out


def parse_concept(path: Path) -> Concept | None:
    """Read + parse one concept note. Return None if it has no Definition."""
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    sections = _split_sections(text)

    definition = sections.get("Definition", "").strip()
    if not definition:
        return None  # unusable: nothing to script from

    try:
        source_count = int(fm.get("source_count", "0"))
    except ValueError:
        source_count = 0

    return Concept(
        slug=path.stem,
        path=path,
        title=fm.get("title", path.stem),
        confidence=fm.get("confidence", "low").lower(),
        domain=fm.get("domain", "general").lower(),
        source_count=source_count,
        definition=definition,
        evidence=_bullets(sections.get("Evidence For", "")),
    )


def is_usable(c: Concept) -> bool:
    """Factory-ready: a scriptable Definition plus at least one evidence bullet.

    confidence is intentionally NOT a hard filter (most notes are `low`); callers
    sort on it instead.
    """
    if len(c.definition.split()) < _MIN_DEFINITION_WORDS:
        return False
    return len(c.evidence) >= 1


def select_concepts(
    concepts_dir: Path,
    done_slugs: set[str],
    count: int,
    prefer_confidence: bool = True,
) -> list[Concept]:
    """Glob notes, keep usable+undone ones, sort, return the first `count`."""
    usable: list[Concept] = []
    for path in sorted(concepts_dir.glob("*.md")):
        if path.stem in done_slugs:
            continue
        try:
            c = parse_concept(path)
        except Exception:
            continue  # robustness: skip anything that won't parse/read
        if c is not None and is_usable(c):
            usable.append(c)

    if prefer_confidence:
        usable.sort(
            key=lambda c: (_CONFIDENCE_RANK.get(c.confidence, 3), -c.source_count)
        )
    return usable[:count]


if __name__ == "__main__":
    # Manual smoke check against the real vault; no-op if the dir is absent.
    if not DEFAULT_CONCEPTS_DIR.exists():
        print(f"[skip] concepts dir not found: {DEFAULT_CONCEPTS_DIR}")
    else:
        paths = sorted(DEFAULT_CONCEPTS_DIR.glob("*.md"))
        usable = []
        for p in paths:
            try:
                c = parse_concept(p)
            except Exception:
                continue
            if c is not None and is_usable(c):
                usable.append(c)
        selected = select_concepts(DEFAULT_CONCEPTS_DIR, set(), 5)
        print(f"total .md files : {len(paths)}")
        print(f"usable concepts : {len(usable)}")
        print("first 5 selected:")
        for c in selected:
            print(f"  - {c.slug}  ::  {c.title}  [{c.confidence}]")
