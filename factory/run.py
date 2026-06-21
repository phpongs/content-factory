"""factory.run — pipeline runner CLI for the content-factory layer.

select vault concepts -> write COMPASS bilingual scripts (local LLM)
-> submit each as a video job to the running MPT API -> log to the done-ledger.

This is a THIN layer on top of MoneyPrinterTurbo. It does NOT touch app/ or webui/.
Run:  python -m factory.run --count 5 --lang th --dry-run

Stdlib + requests only. No new deps.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

# ponytail: Windows consoles default to cp1252 and choke on Thai script in our
# previews/logs. Best-effort switch stdout/stderr to UTF-8 (no-op if unsupported).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

# --- sibling modules (built in parallel on other branches) ------------------
# They may be absent in an isolated worktree. Import if present; otherwise bind
# stub fallbacks so the module still loads AND the names stay monkeypatchable in
# tests. ponytail: don't hard-fail on absent siblings — fakes/monkeypatch cover it.
try:  # pragma: no cover - exercised by integration, not unit tests
    from factory.select import DEFAULT_CONCEPTS_DIR, select_concepts
except Exception:  # noqa: BLE001 - any import failure -> usable stub
    DEFAULT_CONCEPTS_DIR = Path("C:/Users/P/Project/lifeos/wiki/concepts")

    def select_concepts(concepts_dir, done_slugs, count, prefer_confidence=True):
        raise RuntimeError("factory.select not available (sibling module not merged)")

try:  # pragma: no cover
    from factory.done_log import DEFAULT_DONE_LOG, append_done, load_done_slugs
except Exception:  # noqa: BLE001
    DEFAULT_DONE_LOG = Path("storage/factory_done.jsonl")

    def load_done_slugs(log_path):
        # ponytail: empty ledger if real one absent — runner still works dry.
        return set()

    def append_done(log_path, slug, task_id, lang):
        raise RuntimeError("factory.done_log not available (sibling module not merged)")

try:  # pragma: no cover
    from factory.script import write_script
except Exception:  # noqa: BLE001
    def write_script(concept, lang="th", *, llm=None):
        raise RuntimeError("factory.script not available (sibling module not merged)")


# --- MPT API mapping --------------------------------------------------------
API_URL = "http://127.0.0.1:8080/api/v1/videos"

# lang code -> (MPT video_language, voice_name). Verified vs app/models/schema.py.
LANG_MAP = {
    "th": ("th-TH", "th-TH-PremwadeeNeural-Female"),
    "en": ("en-US", "en-US-AndrewMultilingualNeural-V2-Male"),
}


def submit_job(
    script_text: str,
    terms: list[str],
    lang: str,
    api_url: str,
    *,
    session=None,
) -> str | None:
    """POST one video job to MPT. Returns task_id, or None on any failure.

    `session` is injectable (a requests.Session-like with .post) for tests.
    Never raises on network errors — one bad job must not kill the batch.
    """
    video_language, voice_name = LANG_MAP.get(lang, LANG_MAP["th"])
    payload = {
        "video_subject": script_text[:80].strip() or "Vault concept",
        "video_script": script_text,
        "video_terms": terms,
        "video_aspect": "9:16",
        "video_language": video_language,
        "voice_name": voice_name,
        "bgm_type": "random",
        "subtitle_enabled": True,
    }
    sess = session or requests
    try:
        resp = sess.post(api_url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # Response shape: {"data": {"task_id": "..."}} — read defensively.
        return (data.get("data") or {}).get("task_id")
    except Exception as e:  # noqa: BLE001 - log + swallow, return None
        print(f"  ! submit failed ({lang}): {e}")
        return None


# MPT task states (app/models/const.py): -1 failed, 1 complete, 4 processing.
_STATE_FAILED, _STATE_COMPLETE = -1, 1


def poll_task(task_id: str, api_url: str, *, session=None, timeout_s: int = 900, interval_s: int = 6) -> bool:
    """Block until an MPT task completes; return True on success, False on fail/timeout.

    Serializing on this avoids concurrent renders colliding on MoviePy's shared
    temp-audio basename (`final-1TEMP_MPY_wvf_snd.mp4`) — the WinError 32 we hit
    when two jobs composed their final clip at once. ponytail: poll, don't thread.
    `session` injectable for tests.
    """
    import time

    sess = session or requests
    # status endpoint is the videos URL with /<task_id> swapped onto /tasks/<id>
    base = api_url.rsplit("/videos", 1)[0]
    status_url = f"{base}/tasks/{task_id}"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            d = (sess.get(status_url, timeout=10).json() or {}).get("data") or {}
        except Exception:  # noqa: BLE001 - transient; retry next tick
            time.sleep(interval_s)
            continue
        state, progress = d.get("state"), d.get("progress", 0)
        if state == _STATE_COMPLETE:
            return True
        if state == _STATE_FAILED:
            print(f"    task {task_id[:8]} FAILED (state -1)")
            return False
        print(f"    …{task_id[:8]} {progress}%")
        time.sleep(interval_s)
    print(f"    task {task_id[:8]} timed out after {timeout_s}s")
    return False


def run_factory(
    count: int,
    lang: str,
    *,
    concepts_dir=None,
    done_log=None,
    api_url: str = API_URL,
    llm=None,
    submit=None,
    wait=None,
    serialize: bool = True,
    dry_run: bool = False,
) -> list[dict]:
    """Orchestrate: select -> script -> submit -> wait -> ledger. Returns result dicts.

    `submit`/`wait`/`llm` are injectable for testing. dry_run makes ZERO network
    calls and ZERO ledger writes — it just prints what WOULD be generated.

    serialize=True (default): submit ONE job, block until it finishes, then the
    next. MPT runs up to 5 renders concurrently, but concurrent MoviePy finals
    collide on a shared temp-audio name on Windows (WinError 32) — so a factory
    that wants every clip to land must render them one at a time.
    """
    done_log_path = Path(done_log) if done_log else DEFAULT_DONE_LOG
    concepts_path = Path(concepts_dir) if concepts_dir else DEFAULT_CONCEPTS_DIR
    do_submit = submit or submit_job
    do_wait = wait or poll_task

    done = load_done_slugs(done_log_path)
    concepts = select_concepts(concepts_path, done, count)

    results: list[dict] = []
    submitted = failed = skipped = 0

    for concept in concepts:
        sr = write_script(concept, lang, llm=llm)
        for langcode, text in sr.scripts():
            if dry_run:
                preview = text.replace("\n", " ")[:60]
                print(f"  [dry] {concept.slug} [{langcode}] would submit: {preview}...")
                results.append(
                    {"slug": concept.slug, "lang": langcode, "task_id": None, "ok": None}
                )
                skipped += 1
                continue

            task_id = do_submit(text, sr.terms, langcode, api_url)
            ok = task_id is not None
            # Block on render completion so the next job doesn't collide with this one.
            if ok and serialize:
                ok = do_wait(task_id, api_url)
            append_done(done_log_path, concept.slug, task_id, langcode)
            mark = "ok" if ok else "FAIL"
            print(f"  [{mark}] {concept.slug} [{langcode}] task_id={task_id}")
            results.append(
                {"slug": concept.slug, "lang": langcode, "task_id": task_id, "ok": ok}
            )
            if ok:
                submitted += 1
            else:
                failed += 1

    if dry_run:
        print(f"\nDRY RUN: {skipped} job(s) would be generated. No calls made.")
    else:
        print(f"\nDone: {submitted} done / {failed} failed.")
    return results


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m factory.run",
        description="Turn vault concepts into MPT short-form video jobs.",
    )
    p.add_argument("--count", type=int, default=5, help="how many concepts to pull")
    p.add_argument("--lang", choices=["th", "en", "both"], default="th")
    p.add_argument("--dry-run", action="store_true", help="preview only, no network")
    p.add_argument("--api-url", default=API_URL, help="MPT videos endpoint")
    p.add_argument("--concepts-dir", default=None, help="override vault concepts dir")
    p.add_argument("--done-log", default=None, help="override done-ledger path")
    args = p.parse_args(argv)

    if not args.dry_run:
        print("Prereqs: (1) MPT API up — `uv run python main.py` (:8080).")
        print("         (2) local Ollama up — `ollama serve` (Gemma model).")

    run_factory(
        count=args.count,
        lang=args.lang,
        concepts_dir=Path(args.concepts_dir) if args.concepts_dir else None,
        done_log=Path(args.done_log) if args.done_log else None,
        api_url=args.api_url,
        dry_run=args.dry_run,
    )
    return 0


def _self_check() -> None:
    """Run when pytest is unavailable: exercise run_factory(dry_run=True) with
    injected fakes and assert ZERO side-effects (no submit, no ledger write).
    """
    import tempfile
    import types

    calls = {"submit": 0, "append": 0}

    def fake_submit(*a, **k):
        calls["submit"] += 1
        raise AssertionError("submit must NOT be called in dry_run")

    def fake_select(concepts_dir, done_slugs, count):
        return [
            types.SimpleNamespace(slug="s1", title="Concept One"),
            types.SimpleNamespace(slug="s2", title="Concept Two"),
        ]

    def fake_write(concept, lang, *, llm=None):
        sr = types.SimpleNamespace(terms=["a", "b"])
        sr.scripts = lambda: [("th", "th-script"), ("en", "en-script")]
        return sr

    def fake_append(*a, **k):
        calls["append"] += 1
        raise AssertionError("append_done must NOT be called in dry_run")

    g = globals()
    saved = (g["select_concepts"], g["write_script"], g["append_done"])
    g["select_concepts"], g["write_script"], g["append_done"] = (
        fake_select,
        fake_write,
        fake_append,
    )
    try:
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "ledger.jsonl"
            res = run_factory(
                count=2, lang="both", done_log=ledger, submit=fake_submit, dry_run=True
            )
            assert calls["submit"] == 0, "dry_run made submit calls"
            assert calls["append"] == 0, "dry_run wrote the ledger"
            assert not ledger.exists(), "dry_run created the ledger file"
            assert len(res) == 4, f"expected 4 preview rows, got {len(res)}"
            assert all(r["task_id"] is None for r in res)
    finally:
        g["select_concepts"], g["write_script"], g["append_done"] = saved
    print("SELF-CHECK OK: dry_run made 0 submit calls, 0 ledger writes, 4 previews.")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
