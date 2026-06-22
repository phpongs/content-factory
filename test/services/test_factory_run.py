"""Unit tests for factory.run — pure pytest, NO network, NO real MPT/LLM.

Does not depend on the sibling modules (select.py / done_log.py / script.py)
importing successfully: we monkeypatch the names on the `factory.run` module
and inject fakes for `submit` and the LLM.

Run:  python -m pytest test/services/test_factory_run.py
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from factory import run as fr


# --- fakes ------------------------------------------------------------------
def _always_done(task_id, api_url):
    """Stand-in for poll_task: pretend the render finished successfully (no network)."""
    return True


def _fake_concepts():
    return [
        types.SimpleNamespace(slug="alpha", title="Alpha Concept", terms=["x"]),
        types.SimpleNamespace(slug="beta", title="Beta Concept", terms=["y"]),
    ]


def _make_fake_script(terms):
    """A ScriptResult-like object: has .terms and .scripts() -> list[(lang, text)]."""
    def factory(concept, lang, *, llm=None):
        sr = types.SimpleNamespace(slug=concept.slug, terms=terms)
        if lang == "both":
            pairs = [("th", f"TH:{concept.slug}"), ("en", f"EN:{concept.slug}")]
        else:
            pairs = [(lang, f"{lang.upper()}:{concept.slug}")]
        sr.scripts = lambda: pairs
        return sr
    return factory


class _RecordingSubmit:
    def __init__(self, task_id="task-123"):
        self.calls = []
        self.task_id = task_id

    def __call__(self, text, terms, lang, api_url, *, materials=None):
        self.calls.append({"text": text, "terms": terms, "lang": lang, "api_url": api_url, "materials": materials})
        return self.task_id


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Patch select/write/append on the factory.run module to safe fakes."""
    monkeypatch.setattr(fr, "select_concepts", lambda *a, **k: _fake_concepts())
    monkeypatch.setattr(fr, "load_done_slugs", lambda *a, **k: set())
    monkeypatch.setattr(fr, "write_script", _make_fake_script(["kw1", "kw2"]))
    # append_done writes a line to the ledger so we can assert on side-effects.
    appended = []

    def fake_append(log_path, slug, task_id, lang):
        appended.append((slug, task_id, lang))
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{slug},{task_id},{lang}\n")

    monkeypatch.setattr(fr, "append_done", fake_append)
    return types.SimpleNamespace(appended=appended, tmp=tmp_path)


# --- dry_run: zero side-effects ---------------------------------------------
def test_dry_run_makes_no_submit_and_no_ledger_writes(patched):
    ledger = patched.tmp / "done.jsonl"

    def exploding_submit(*a, **k):
        raise AssertionError("submit must not be called during dry_run")

    res = fr.run_factory(
        count=2, lang="both", done_log=ledger, submit=exploding_submit, dry_run=True
    )

    assert patched.appended == []            # no append_done calls
    assert not ledger.exists()               # ledger never created
    assert len(res) == 4                      # 2 concepts x 2 langs, preview rows
    assert all(r["task_id"] is None for r in res)


# --- normal run: one submit per (concept x language) ------------------------
def test_normal_run_both_langs_submits_four_times(patched):
    ledger = patched.tmp / "done.jsonl"
    submit = _RecordingSubmit()

    res = fr.run_factory(
        count=2, lang="both", done_log=ledger, submit=submit, wait=_always_done
    )

    assert len(submit.calls) == 4            # 2 concepts x 2 langs
    assert len(res) == 4
    assert all(r["ok"] for r in res)
    assert {c["lang"] for c in submit.calls} == {"th", "en"}
    assert len(patched.appended) == 4         # ledger written once per job


def test_normal_run_single_lang_submits_twice(patched):
    ledger = patched.tmp / "done.jsonl"
    submit = _RecordingSubmit()

    fr.run_factory(count=2, lang="th", done_log=ledger, submit=submit, wait=_always_done)

    assert len(submit.calls) == 2            # 2 concepts x 1 lang
    assert all(c["lang"] == "th" for c in submit.calls)


# --- submit_job payload correctness -----------------------------------------
class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.posted = None

    def post(self, url, json=None, timeout=None):
        self.posted = {"url": url, "json": json, "timeout": timeout}
        return _FakeResponse(self._payload)


def test_submit_job_builds_correct_payload_th():
    sess = _FakeSession({"data": {"task_id": "t1"}})

    task_id = fr.submit_job("hello script", ["term1", "term2"], "th", fr.API_URL, session=sess)

    assert task_id == "t1"
    body = sess.posted["json"]
    assert body["video_aspect"] == "9:16"
    assert body["video_language"] == "th-TH"
    assert body["voice_name"] == "th-TH-PremwadeeNeural-Female"
    assert body["video_script"] == "hello script"
    assert body["video_terms"] == ["term1", "term2"]
    assert body["subtitle_enabled"] is True
    assert sess.posted["timeout"] == 15


def test_submit_job_maps_english_voice():
    sess = _FakeSession({"data": {"task_id": "t2"}})

    task_id = fr.submit_job("hi", ["k"], "en", fr.API_URL, session=sess)

    assert task_id == "t2"
    assert sess.posted["json"]["video_language"] == "en-US"
    assert sess.posted["json"]["voice_name"] == "en-US-AndrewMultilingualNeural-V2-Male"


# --- submit failure: returns None, batch continues --------------------------
class _ExplodingSession:
    def post(self, *a, **k):
        raise ConnectionError("MPT server down")


def test_submit_job_returns_none_on_network_error():
    task_id = fr.submit_job("script", ["k"], "th", fr.API_URL, session=_ExplodingSession())
    assert task_id is None


def test_batch_continues_when_a_submit_fails(patched):
    ledger = patched.tmp / "done.jsonl"

    def flaky_submit(text, terms, lang, api_url, *, materials=None):
        # First call fails (returns None), the rest succeed.
        if len(flaky_submit.seen) == 0:
            flaky_submit.seen.append(lang)
            return None
        flaky_submit.seen.append(lang)
        return "task-ok"

    flaky_submit.seen = []

    res = fr.run_factory(
        count=2, lang="th", done_log=ledger, submit=flaky_submit, wait=_always_done
    )

    assert len(res) == 2                       # batch did not abort on first failure
    assert res[0]["ok"] is False and res[0]["task_id"] is None
    assert res[1]["ok"] is True and res[1]["task_id"] == "task-ok"


# --- serialize: a failed render marks the job failed even if submit succeeded ---
def test_serialize_waits_and_failed_render_marks_not_ok(patched):
    ledger = patched.tmp / "done.jsonl"
    submit = _RecordingSubmit()
    waited = []

    def failing_wait(task_id, api_url):
        waited.append(task_id)
        return False  # render failed downstream

    # the fake select returns 2 concepts regardless of count; th = 1 job each.
    res = fr.run_factory(
        count=2, lang="th", done_log=ledger, submit=submit, wait=failing_wait
    )

    assert len(submit.calls) == 2          # both jobs submitted
    assert len(waited) == 2               # and we waited on each render
    assert all(r["ok"] is False for r in res)        # render-fail flips ok to False
    assert all(r["task_id"] is not None for r in res)  # ...but task_ids still recorded
