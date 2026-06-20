"""Append-only JSONL ledger of generated concepts, so we never re-generate one.

Each line is one JSON object:
    {"slug": "...", "task_id": "...", "lang": "...", "ts": "<ISO UTC>"}
Stdlib only.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DONE_LOG = Path("C:/Users/P/Project/content-factory/storage/factory_done.jsonl")


def load_done_slugs(log_path: Path) -> set[str]:
    """Return the set of slugs recorded in the ledger.

    Missing file -> empty set. Blank or corrupt lines are skipped, so a partially
    written tail line can never crash a run.
    """
    if not log_path.exists():
        return set()
    slugs: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue  # ponytail: tolerate corrupt/partial lines, just skip them
        slug = obj.get("slug") if isinstance(obj, dict) else None
        if slug:
            slugs.add(slug)
    return slugs


def append_done(log_path: Path, slug: str, task_id: str | None, lang: str) -> None:
    """Append one record with an ISO-8601 UTC timestamp. Creates parent dir."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "slug": slug,
        "task_id": task_id,
        "lang": lang,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    # Self-check: write 2 entries to a temp file, reload, assert the slug set.
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "factory_done.jsonl"
    append_done(tmp, "alpha-concept", "task-1", "en")
    append_done(tmp, "beta-concept", None, "th")
    got = load_done_slugs(tmp)
    assert got == {"alpha-concept", "beta-concept"}, got
    # A corrupt trailing line must be skipped, not crash.
    with tmp.open("a", encoding="utf-8") as f:
        f.write("{not valid json\n")
    assert load_done_slugs(tmp) == {"alpha-concept", "beta-concept"}
    print(f"OK  ({tmp})")
