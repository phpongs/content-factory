# Content Factory

A thin layer **on top of** MoneyPrinterTurbo (MPT) that turns the personal LifeOS
vault (`wiki/concepts/`) into short-form TikTok videos in our COMPASS voice.

We did **not** fork or modify MPT internals — `app/` and `webui/` are untouched
upstream. Everything we own lives in `factory/`; we talk to MPT only over its HTTP API.

## Pipeline

```
wiki/concepts/*.md
      |  select_concepts()  (skip slugs already in the done-log)
      v
  COMPASS bilingual script  (write_script -> local Gemma via Ollama)
      v
  POST /api/v1/videos        (MPT renders: stock footage + TTS + subtitles + BGM)
      v
  storage/factory_done.jsonl (done-ledger: append slug + task_id + lang)
```

## Prerequisites

1. **MPT API running** — `uv run python main.py` (serves `http://127.0.0.1:8080`).
2. **Local Ollama running** — `ollama serve`, with a Gemma model pulled.
   Model is read from `FACTORY_LLM_MODEL` (default `gemma4:latest`).
   Replies are requested in Ollama `format=json` mode and parsed with up to
   3 retries, since local models occasionally emit malformed/truncated JSON.
3. **Vault present** at `C:/Users/P/Project/lifeos/wiki/concepts/`.

## Usage

`factory/__init__.py` makes `factory` a package, so run it with `python -m`:

```bash
# Dry run — preview which concepts + scripts WOULD be submitted, no MPT calls,
# no ledger writes. NOTE: the script step still calls the local LLM (Ollama must
# be up) unless you inject a stub llm — dry-run only skips the network/ledger,
# not script generation.
python -m factory.run --count 5 --lang th --dry-run

# Real run — submits a video job per (concept x language) to MPT.
python -m factory.run --count 10 --lang both
```

Flags: `--count N` (default 5), `--lang {th,en,both}` (default th),
`--dry-run`, `--api-url URL`, `--concepts-dir DIR`, `--done-log PATH`.

## Files

| File | Role |
|---|---|
| `factory/select.py` | Read `wiki/concepts/`, skip done slugs, pick N concepts (confidence-ranked). |
| `factory/script.py` | Write the COMPASS bilingual script per concept via local Gemma. |
| `factory/run.py` | This CLI: orchestrates select -> script -> submit -> ledger. |
| `factory/done_log.py` | Load/append the done-ledger (idempotency). |
| `storage/factory_done.jsonl` | The ledger — one JSON line per submitted job. |

## Design notes

- **Why a ledger** — re-runs are idempotent. `select_concepts` skips any slug
  already in `factory_done.jsonl`, so repeated runs never produce duplicate videos.
- **Why a local LLM** — script generation is free and private (delegation policy);
  no per-call API cost, no vault content leaving the machine.
- **Why we don't touch `app/`** — MPT is upstream we must be able to pull from.
  Keeping everything in `factory/` and crossing only the HTTP boundary means
  upstream merges never conflict with our layer.
- **ponytail shortcuts** — one job per language, submitted sequentially. Batching
  or async only if volume grows. A single failed submit logs and returns `None`;
  the batch continues rather than aborting.
