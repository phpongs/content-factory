"""Pure-pytest tests for the COMPASS script writer. No live network, no MPT imports.

The LLM call is injected as a fake callable returning canned JSON, so these tests
exercise prompt assembly -> JSON parsing -> ScriptResult shaping in isolation.

Run: python -m pytest test/services/test_factory_script.py
"""

import sys
import types
from pathlib import Path

import pytest

# Make the repo root importable so `factory` resolves regardless of pytest rootdir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from factory.script import ScriptParseError, ScriptResult, write_script


def make_concept():
    return types.SimpleNamespace(
        slug="blue-ocean",
        title="Blue Ocean Strategy",
        definition="Create uncontested market space instead of competing in a crowded red ocean.",
        evidence=["Cirque du Soleil sidestepped circus price wars"],
        domain="business",
    )


def fake(json_str):
    """Return an llm-shaped callable that ignores the prompt and yields canned JSON."""
    return lambda prompt: json_str


def test_th_sets_only_thai():
    r = write_script(
        make_concept(),
        "th",
        llm=fake('{"script": "เลิกแข่งในตลาดที่เลือดสาด", "terms": ["ocean", "arena", "chess board", "city skyline"]}'),
    )
    assert isinstance(r, ScriptResult)
    assert r.script_th == "เลิกแข่งในตลาดที่เลือดสาด"
    assert r.script_en is None
    assert len(r.terms) == 4


def test_en_sets_only_english():
    r = write_script(
        make_concept(),
        "en",
        llm=fake('{"script": "Stop competing where everyone bleeds.", "terms": ["ocean waves", "empty arena", "spotlight", "blueprint", "chess board"]}'),
    )
    assert r.script_en == "Stop competing where everyone bleeds."
    assert r.script_th is None
    assert len(r.terms) == 5


def test_both_sets_both_scripts():
    r = write_script(
        make_concept(),
        "both",
        llm=fake('{"script_th": "เลิกแข่งในตลาดเดิม", "script_en": "Stop competing where everyone bleeds.", "terms": ["ocean", "arena", "spotlight", "blueprint"]}'),
    )
    assert r.script_th == "เลิกแข่งในตลาดเดิม"
    assert r.script_en == "Stop competing where everyone bleeds."
    assert r.lang == "both"


def test_fenced_json_is_parsed():
    fenced = '```json\n{"script": "Sharp line.", "terms": ["a", "b", "c", "d"]}\n```'
    r = write_script(make_concept(), "en", llm=fake(fenced))
    assert r.script_en == "Sharp line."
    assert r.terms == ["a", "b", "c", "d"]


def test_json_embedded_in_prose_is_parsed():
    # first { .. last } extraction should survive leading/trailing chatter
    messy = 'Sure! Here you go: {"script": "Lever, not trick.", "terms": ["x", "y", "z", "w"]} hope that helps'
    r = write_script(make_concept(), "en", llm=fake(messy))
    assert r.script_en == "Lever, not trick."


def test_malformed_json_raises():
    with pytest.raises(ScriptParseError):
        write_script(make_concept(), "en", llm=fake("totally not json"))


def test_scripts_returns_correct_pairs():
    r = write_script(
        make_concept(),
        "both",
        llm=fake('{"script_th": "ไทย", "script_en": "English", "terms": ["a", "b", "c", "d"]}'),
    )
    assert r.scripts() == [("th", "ไทย"), ("en", "English")]


def test_scripts_single_language_pair():
    r = write_script(
        make_concept(),
        "th",
        llm=fake('{"script": "ไทยล้วน", "terms": ["a", "b", "c", "d"]}'),
    )
    assert r.scripts() == [("th", "ไทยล้วน")]


def test_prompt_carries_compass_voice_and_concept():
    captured = {}

    def spy(prompt):
        captured["p"] = prompt
        return '{"script": "ok", "terms": ["a", "b", "c", "d"]}'

    write_script(make_concept(), "en", llm=spy)
    p = captured["p"]
    # the voice is the deliverable — make sure it actually reaches the model
    assert "COMPASS" in p
    assert "FIRST PRINCIPLES" in p
    assert "Blue Ocean Strategy" in p
    # and the anti-patterns we're replacing are explicitly forbidden
    assert "follow for more" in p
    assert "Stop scrolling" in p
