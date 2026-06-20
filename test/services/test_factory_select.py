"""Tests for the content-factory concept selection + done-log ledger.

Pure pytest, stdlib + pytest only. NO imports from app/. Deterministic: every
fixture file is written into tmp_path, so the real vault is never touched.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from factory.done_log import append_done, load_done_slugs
from factory.select import is_usable, parse_concept, select_concepts

USABLE = """\
---
title: Blue Ocean Strategy
type: concept
domain: business
confidence: medium
source_count: 3
tags: [concept]
---

# Blue Ocean Strategy

## Definition
This strategy focuses on creating uncontested market space rather than competing
in existing industries, making the competition irrelevant by creating new demand.

## Evidence For
- Focus on creating uncontested market space rather than competing.
- Aims to make competition irrelevant by creating new demand.

## Evidence Against
"""

# Has Evidence but the Definition heading body is empty -> unusable.
EMPTY_DEF = """\
---
title: Empty Def
domain: general
confidence: low
source_count: 1
---

# Empty Def

## Definition

## Evidence For
- Some evidence bullet that exists.
"""

# Real Definition but zero evidence bullets -> unusable.
NO_EVIDENCE = """\
---
title: No Evidence
domain: psychology
confidence: high
source_count: 2
---

# No Evidence

## Definition
This is a perfectly long definition with well over a dozen words so the word
count gate passes cleanly, leaving only the missing evidence to fail it.

## Evidence For
"""


def _write(dir_path: Path, name: str, content: str) -> Path:
    p = dir_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_concept_extracts_fields(tmp_path):
    p = _write(tmp_path, "blue-ocean-strategy.md", USABLE)
    c = parse_concept(p)
    assert c is not None
    assert c.slug == "blue-ocean-strategy"
    assert c.title == "Blue Ocean Strategy"
    assert c.confidence == "medium"
    assert c.source_count == 3
    assert c.definition.startswith("This strategy focuses on creating uncontested")
    assert len(c.evidence) == 2
    assert c.evidence[0] == "Focus on creating uncontested market space rather than competing."


def test_is_usable_gates(tmp_path):
    good = parse_concept(_write(tmp_path, "good.md", USABLE))
    no_ev = parse_concept(_write(tmp_path, "no-ev.md", NO_EVIDENCE))
    # Empty Definition -> parse_concept returns None (unusable by construction).
    empty = parse_concept(_write(tmp_path, "empty.md", EMPTY_DEF))

    assert is_usable(good) is True
    assert empty is None
    assert no_ev is not None and is_usable(no_ev) is False


def test_select_concepts_excludes_done_and_respects_count(tmp_path):
    _write(tmp_path, "a.md", USABLE)
    _write(tmp_path, "b.md", USABLE)
    _write(tmp_path, "c.md", USABLE)
    _write(tmp_path, "empty.md", EMPTY_DEF)  # never selectable

    # done excludes "a"; count caps the rest.
    selected = select_concepts(tmp_path, done_slugs={"a"}, count=2)
    slugs = {c.slug for c in selected}
    assert len(selected) == 2
    assert "a" not in slugs
    assert slugs <= {"b", "c"}


def test_done_log_roundtrip_and_corrupt_line(tmp_path):
    log = tmp_path / "nested" / "factory_done.jsonl"  # parent dir must be created
    assert load_done_slugs(log) == set()  # missing file -> empty

    append_done(log, "alpha", "task-1", "en")
    append_done(log, "beta", None, "th")
    assert load_done_slugs(log) == {"alpha", "beta"}

    with log.open("a", encoding="utf-8") as f:
        f.write("\n{garbage not json\n")  # blank + corrupt lines
    assert load_done_slugs(log) == {"alpha", "beta"}
