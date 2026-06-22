"""Turn a vault concept into a short-form video script + stock-footage search terms.

Replaces the old generic-viral-hype batch script ("Hit follow for more
life-changing secrets!") with a COMPASS-voiced writer: first-principles,
leverage, signal>noise, inversion. The LLM call is injectable so this module
is unit-testable without a live model, and so the orchestrator (frontier) can
swap in a higher-capability model when it wants to.

stdlib + requests only. Does NOT import app/ — the Concept is duck-typed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import requests

# Voice TTS picks (MPT edge-tts voice ids), chosen per language.
VOICE_TH = "th-TH-PremwadeeNeural-Female"
VOICE_EN = "en-US-AndrewMultilingualNeural-V2-Male"

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


class ScriptParseError(ValueError):
    """Raised when the model's reply can't be coerced into the expected JSON."""


# --- The voice. This is the point of the module. ----------------------------
# COMPASS framework baked into a system prompt. Read CLAUDE.md "COMPASS filters".
SYSTEM_PROMPT = """\
You are a short-form video scriptwriter for a sharp, founder-minded audience. \
You write through the COMPASS lens. Every script must obey these rules:

1. FIRST PRINCIPLES. Strip the idea to its root mechanism — WHY it works at the \
causal level — not a list of surface tips or tactics. Explain the lever, not the trick.
2. LEVERAGE. Point the viewer at actions with asymmetric upside (skills, systems, \
ownership, code, audience — things that pay while you sleep). Never frame success \
as trading time for money linearly ("work harder / more hours" is banned).
3. SIGNAL > NOISE. Maximum insight per second. Cut every filler word, hedge, and \
throat-clear. If a sentence doesn't change how the viewer thinks or acts, delete it.
4. INVERSION. Where it lands harder, frame the lesson as a failure to avoid \
("here's what quietly kills most attempts") instead of a feel-good to-do.
5. HOOK FIRST. The opening line must be a substantive hook: a surprising truth, a \
counterintuitive inversion, or a sharp claim that reframes the topic. \
NEVER use empty attention-bait like "Stop scrolling!", "You won't believe...", or \
"Here's a secret nobody tells you".
6. TONE. Smart, direct, zero fluff. Talk to the viewer as a capable peer who is busy \
and intelligent — not as a guru talking down, not as a hype-man. A clean insight \
beats excitement. No emojis in the script body. No hashtags.
7. ENDING. Close on one crisp, memorable takeaway the viewer can act on or remember. \
NEVER end with "follow for more", "hit that follow button", "like and subscribe", or \
any engagement-bait call to follow.

Length: a 60-75 second short — roughly 8-12 punchy sentences. Develop the idea
across a few beats (hook → the mechanism → an example or inversion → takeaway),
but every sentence still earns its place. Not an essay, not a single paragraph.

You also output 4-6 stock-footage search terms for B-roll: concrete, visual, \
filmable English nouns/scenes a Pexels search would return real clips for \
(e.g. "chess board", "city skyline night", "person sketching whiteboard"). \
Avoid abstractions like "success", "growth", "mindset" — they don't match footage.

Output STRICT JSON only. No markdown, no commentary, no code fences."""


def _user_prompt(title: str, definition: str, evidence: list[str], domain: str, lang: str) -> str:
    """Assemble the concept-specific user turn + the language/JSON-shape contract."""
    ev = "\n".join(f"- {e}" for e in (evidence or [])) or "- (none provided)"

    if lang == "both":
        shape = (
            'Return STRICT JSON: {"script_th": "<Thai script>", '
            '"script_en": "<English script>", "terms": ["term1", ...]}.\n'
            "script_th: natural conversational Thai for Thai TikTok (NOT textbook/translated-sounding).\n"
            "script_en: casual-professional English.\n"
            "terms: 4-6 English stock-footage search keywords (shared for both)."
        )
    elif lang == "en":
        shape = (
            'Return STRICT JSON: {"script": "<English script>", "terms": ["term1", ...]}.\n'
            "script: casual-professional English.\n"
            "terms: 4-6 English stock-footage search keywords."
        )
    else:  # "th" (default)
        shape = (
            'Return STRICT JSON: {"script": "<Thai script>", "terms": ["term1", ...]}.\n'
            "script: natural conversational Thai for Thai TikTok (NOT textbook/translated-sounding).\n"
            "terms: 4-6 English stock-footage search keywords."
        )

    return (
        f"CONCEPT: {title}\n"
        f"DOMAIN: {domain}\n"
        f"DEFINITION: {definition}\n"
        f"EVIDENCE / SUPPORTING POINTS:\n{ev}\n\n"
        f"Write the short-form script in the COMPASS voice for the concept above.\n\n"
        f"{shape}"
    )


def _build_prompt(concept, lang: str) -> str:
    """Combine system + user into a single prompt string for a /api/generate model."""
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"=== TASK ===\n"
        f"{_user_prompt(concept.title, concept.definition, list(concept.evidence), concept.domain, lang)}"
    )


def _ollama_llm(prompt: str) -> str:
    # ponytail: local-Ollama path. The orchestrator (frontier) may swap `llm` for an
    # MCP/Gemma-backed callable the subagent can't invoke; this is just the runtime default.
    model = os.environ.get("FACTORY_LLM_MODEL", "gemma4:latest")
    try:
        resp = requests.post(
            OLLAMA_URL,
            # format=json: Ollama constrains decoding to valid JSON, so the model
            # can't emit unescaped quotes mid-string (live Gemma did, breaking parse).
            json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=120,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Local Ollama call failed ({OLLAMA_URL}, model={model}): {e}") from e
    return resp.json().get("response", "")


def _extract_json(raw: str) -> dict:
    """Robustly pull a JSON object out of a model reply: strip ``` fences, take first { .. last }."""
    text = (raw or "").strip()
    if text.startswith("```"):
        # drop opening fence (``` or ```json) and trailing fence
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ScriptParseError(f"No JSON object found in model reply: {raw[:300]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise ScriptParseError(f"Could not parse model JSON ({e}): {raw[:300]!r}") from e


@dataclass
class ScriptResult:
    slug: str
    lang: str
    script_th: str | None
    script_en: str | None
    terms: list[str] = field(default_factory=list)

    def scripts(self) -> list[tuple[str, str]]:
        """[(langcode, script), ...] for whichever scripts are present — one MPT job each."""
        out: list[tuple[str, str]] = []
        if self.script_th:
            out.append(("th", self.script_th))
        if self.script_en:
            out.append(("en", self.script_en))
        return out


def _parse_reply(raw: str, lang: str, slug: str) -> ScriptResult:
    """Coerce one model reply into a ScriptResult, or raise ScriptParseError."""
    data = _extract_json(raw)

    terms = data.get("terms") or []
    if not isinstance(terms, list):
        raise ScriptParseError(f"'terms' is not a list: {raw[:300]!r}")
    terms = [str(t).strip() for t in terms if str(t).strip()]
    # A clip with no B-roll terms falls back to near-empty footage. Treat a too-thin
    # term list as a parse failure so write_script re-rolls instead of shipping it.
    if len(terms) < 3:
        raise ScriptParseError(f"too few B-roll terms ({len(terms)}): {raw[:300]!r}")

    if lang == "both":
        script_th = data.get("script_th")
        script_en = data.get("script_en")
        if not script_th or not script_en:
            raise ScriptParseError(f"'both' reply missing script_th/script_en: {raw[:300]!r}")
    else:
        script = data.get("script")
        if not script:
            raise ScriptParseError(f"reply missing 'script': {raw[:300]!r}")
        script_th = script if lang == "th" else None
        script_en = script if lang == "en" else None

    return ScriptResult(slug=slug, lang=lang, script_th=script_th, script_en=script_en, terms=terms)


def write_script(concept, lang: str = "th", *, llm=None, attempts: int = 3) -> ScriptResult:
    """Generate a COMPASS-voiced short-form script + stock terms for a concept.

    concept: any object with .slug .title .definition .evidence .domain (duck-typed).
    lang: "th" | "en" | "both".
    llm:  callable (prompt:str) -> str. Defaults to the local Ollama HTTP path.
    attempts: retry count — local LLMs are non-deterministic and occasionally
        emit truncated/half-formed JSON or skip a key; a re-roll fixes most.
    """
    if lang not in ("th", "en", "both"):
        raise ValueError(f"lang must be 'th', 'en', or 'both', got {lang!r}")
    if llm is None:
        llm = _ollama_llm

    prompt = _build_prompt(concept, lang)
    last_err: ScriptParseError | None = None
    for _ in range(max(1, attempts)):
        # ponytail: re-roll on parse failure — cheapest fix for flaky local-LLM JSON.
        try:
            return _parse_reply(llm(prompt), lang, concept.slug)
        except ScriptParseError as e:
            last_err = e
    raise last_err  # type: ignore[misc]


if __name__ == "__main__":
    # Self-check: runs the full parse path with an inline fake llm (no network, no pytest).
    # python factory/script.py
    import types

    concept = types.SimpleNamespace(
        slug="blue-ocean",
        title="Blue Ocean Strategy",
        definition="Create uncontested market space instead of fighting in a bloody red ocean.",
        evidence=["Cirque du Soleil skipped circus price wars", "Value innovation lowers cost AND raises value"],
        domain="business",
    )

    def fake_th(prompt: str) -> str:
        assert "COMPASS" in prompt and "Blue Ocean" in prompt, "prompt missing voice/concept"
        return '```json\n{"script": "ตลาดที่เลือดสาด คุณไม่มีวันชนะ...", "terms": ["ocean waves", "empty arena", "chess board", "city skyline"]}\n```'

    def fake_both(prompt: str) -> str:
        return '{"script_th": "เลิกแข่งในตลาดเดิม", "script_en": "Stop competing where everyone bleeds.", "terms": ["ocean", "arena", "spotlight", "blueprint"]}'

    r = write_script(concept, "th", llm=fake_th)
    assert r.script_th and r.script_en is None, "th: only script_th expected"
    assert len(r.terms) == 4, f"expected 4 terms, got {r.terms}"
    assert r.scripts() == [("th", r.script_th)], r.scripts()

    r2 = write_script(concept, "both", llm=fake_both)
    assert r2.script_th and r2.script_en, "both: both scripts expected"
    assert [c for c, _ in r2.scripts()] == ["th", "en"], r2.scripts()

    try:
        write_script(concept, "en", llm=lambda p: "not json at all")
    except ScriptParseError:
        pass
    else:  # pragma: no cover
        raise AssertionError("malformed JSON should raise ScriptParseError")

    print("factory/script.py self-check OK")
