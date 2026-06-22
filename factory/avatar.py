"""factory.avatar — render a talking-head HOOK clip via ComfyUI InfiniteTalk.

The brand avatar (a fixed face image) is animated to lip-sync the hook line of a
script, producing a short ~5-8s mp4. That clip is fed to MPT as a local material
named `*__pin_first__*` so MPT opens the video with it (see the patch in
app/services/video.py), then continues with B-roll + the full voiceover.

Only the hook is rendered as talking-head — InfiniteTalk is slow (~120s for ~3s
at 4 steps), and 80% of retention is the first seconds, so animating just the
hook is the high-leverage move.

stdlib + requests. Talks to a running ComfyUI (default :8000) and edge-tts for TTS.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path

import requests

COMFY = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8000")
COMFY_INPUT = Path(os.environ.get("COMFYUI_INPUT", r"C:/Users/P/.ComfyUI/input"))
COMFY_OUTPUT = Path(os.environ.get("COMFYUI_OUTPUT", r"C:/Users/P/.ComfyUI/output"))
_HERE = Path(__file__).resolve().parent.parent  # content-factory root
WORKFLOW = _HERE / "workflows" / "video_infinitetalk.json"
BRAND_AVATAR = _HERE / "assets" / "brand_avatar.png"

# Female voice that matches the brand avatar (the male-voice mismatch bug, fixed).
AVATAR_VOICE = "en-US-AvaMultilingualNeural"


def _tts(text: str, out_path: Path, voice: str = AVATAR_VOICE) -> None:
    """Synthesize `text` to mp3 with edge-tts (sync wrapper)."""
    import asyncio

    import edge_tts

    async def _go():
        await edge_tts.Communicate(text, voice).save(str(out_path))

    asyncio.run(_go())


def _poll(prompt_id: str, timeout_s: int = 1200, interval_s: int = 6) -> dict | None:
    """Block until a ComfyUI prompt finishes. Returns its history entry or None."""
    deadline = time.time() + timeout_s
    url = f"{COMFY}/history/{prompt_id}"
    while time.time() < deadline:
        try:
            h = (requests.get(url, timeout=10).json() or {}).get(prompt_id)
        except Exception:  # noqa: BLE001
            time.sleep(interval_s)
            continue
        if h:
            status = (h.get("status") or {}).get("status_str")
            if status == "success":
                return h
            if status == "error":
                # surface the node error for debugging
                for typ, p in (h.get("status") or {}).get("messages", []):
                    if typ == "execution_error":
                        raise RuntimeError(
                            f"ComfyUI node {p.get('node_id')} {p.get('node_type')}: "
                            f"{p.get('exception_message')}"
                        )
                raise RuntimeError(f"ComfyUI prompt {prompt_id} failed")
        time.sleep(interval_s)
    raise TimeoutError(f"ComfyUI prompt {prompt_id} timed out after {timeout_s}s")


def render_hook(hook_text: str, dest: Path, *, avatar: Path | None = None) -> Path:
    """Render a talking-head clip of `hook_text` and copy it to `dest`.

    `dest` should carry the `__pin_first__` marker so MPT opens with it.
    Returns the final path. Requires ComfyUI running with InfiniteTalk models.
    """
    avatar = avatar or BRAND_AVATAR
    if not avatar.exists():
        raise FileNotFoundError(f"brand avatar missing: {avatar}")
    if not WORKFLOW.exists():
        raise FileNotFoundError(f"InfiniteTalk workflow missing: {WORKFLOW}")

    # stage avatar + hook audio into ComfyUI's input dir (the workflow refers to
    # them by bare filename). ponytail: fixed names, one render at a time.
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(avatar, COMFY_INPUT / "avatar.png")
    _tts(hook_text, COMFY_INPUT / "speech.mp3")

    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    # workflow already points LoadImage->avatar.png, LoadAudio->speech.mp3.

    client_id = str(uuid.uuid4())
    r = requests.post(
        f"{COMFY}/prompt",
        json={"prompt": wf, "client_id": client_id},
        timeout=30,
    )
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]

    hist = _poll(prompt_id)
    # find the SaveVideo output filename
    out_rel = None
    for _nid, o in (hist.get("outputs") or {}).items():
        for imgs in o.get("images", []):
            if str(imgs.get("filename", "")).endswith(".mp4"):
                sub = imgs.get("subfolder", "")
                out_rel = Path(sub) / imgs["filename"]
                break
    if out_rel is None:
        raise RuntimeError(f"no mp4 output from prompt {prompt_id}")

    src = COMFY_OUTPUT / out_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return dest


def split_for_segments(script: str, n: int = 4) -> list[str]:
    """Split a script into ~n speakable chunks on sentence boundaries.

    Each chunk becomes one avatar segment woven through the video. Sentences are
    grouped greedily so chunks are roughly even and none is a stray fragment.
    """
    import re

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script.strip()) if s.strip()]
    if len(sentences) <= n:
        return sentences
    # greedy even grouping
    per = len(sentences) / n
    chunks, cur, target = [], [], per
    for idx, s in enumerate(sentences, 1):
        cur.append(s)
        if idx >= target and len(chunks) < n - 1:
            chunks.append(" ".join(cur))
            cur = []
            target += per
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def render_segments(script: str, slug: str, dest_dir: Path, *, n: int = 4,
                    avatar: Path | None = None) -> list[str]:
    """Render `n` avatar segments for `script`, named so MPT weaves them in order.

    Returns the list of filenames (each carrying `__avatarseg__` + a zero-padded
    index) placed in `dest_dir`. Best-effort: a failed segment is skipped, the
    batch still produces the rest. ponytail: sequential render — InfiniteTalk is
    single-GPU anyway.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    chunks = split_for_segments(script, n)
    out: list[str] = []
    for i, chunk in enumerate(chunks):
        dest = dest_dir / f"{slug}__avatarseg__{i:02d}.mp4"
        try:
            render_hook(chunk, dest, avatar=avatar)
            out.append(dest.name)
            print(f"    avatar seg {i}: {dest.name}")
        except Exception as e:  # noqa: BLE001 - skip a bad segment, keep going
            print(f"    ! avatar seg {i} failed: {e}")
    return out


if __name__ == "__main__":
    # Smoke test: render a hook clip with the brand avatar. Requires ComfyUI up.
    import sys

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    out = _HERE / "storage" / "avatars" / "hook__pin_first__demo.mp4"
    text = "Most people chase resilience. The real edge is becoming antifragile."
    print(f"rendering hook -> {out}")
    p = render_hook(text, out)
    print(f"OK: {p} ({p.stat().st_size // 1024} KB)")
