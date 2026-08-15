# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small collection of LLM feature demos, each with its own page, sharing one FastAPI backend. No build step on the frontend, no test suite. Currently:

- **Content Moderation** — checks text against Mistral's moderation model.
- **LLM Quirks** — small, reproducible cases where a model's behavior isn't what you'd expect, run live against the model on demand.
- **Token Efficiency** — compares classify-then-answer (2 small calls) against stuffing an entire product catalog into one prompt (1 big call), showing real token usage from the API for both, side by side.
- **Tool Calling** — the user defines functions (name, description, parameters, and a fixed mock result) in the browser; the model decides whether/what to call, and each call resolves to that user-typed mock result verbatim (no real code execution).

## Running it

```bash
pip install -r backend/requirements.txt
cp .env.example .env   # then fill in MISTRAL_API_KEY
uvicorn app.main:app --reload --app-dir backend
```

Open http://localhost:8000. There is no lint or test command configured — verify changes by running the server and hitting the relevant page/endpoint (a `.venv` already exists at the repo root).

Requires **Python 3.10+** (the codebase uses `X | None` union type hints) — use the repo's `.venv` (3.12) rather than an older system `python3`. Note `config.py` loads `.env` via a CWD-relative path (`env_file=".env"`), so it must sit next to wherever you launch `uvicorn` from — the repo root, per the command above.

## Architecture

**Backend** (`backend/app/`): FastAPI app. Each feature is a self-contained vertical slice under `backend/app/features/<name>/`:
- `router.py` — thin `APIRouter` exposing `/api/<name>/...` endpoints, no logic.
- `schemas.py` — Pydantic request/response models.
- `service.py` — the actual business logic.
- optionally a data file (e.g. `cases.py`, `catalog.py`) acting as the single source of truth for that feature's content, so adding a case/product means editing data, not routing/rendering code.

New feature routers are registered by hand in `backend/app/main.py`. All features share one Mistral client (`backend/app/llm_client.py`) — Mistral exposes an OpenAI-compatible API, so it's just `openai.OpenAI` pointed at Mistral's base URL. Add new thin wrappers there (not per-feature) as new call shapes are needed; there are already four: `run_moderation`, `run_chat_completion` (single-prompt, no usage), `run_chat` (full message list, returns token usage — use this when a feature needs to display/compare token counts, and optionally pass `tools` to enable function/tool calling, surfaced back on `ChatResult.tool_calls`), and `stream_chat_completion` (yields text as it arrives, for slow chain-of-thought answers).

All config (API key, base URL, model names) lives in `backend/app/config.py` via `pydantic-settings`, read from `.env`. Feature code should always go through `get_settings()` rather than hardcoding model names, so there's one place to change credentials/models.

`app.mount("/", StaticFiles(...))` in `main.py` serves `frontend/` and is registered *last* so it only catches paths no API router matched.

**Frontend** (`frontend/`): plain HTML/CSS/JS, no framework, no build step. `index.html` links out to one page per feature under `frontend/features/<name>/`. Shared fetch helpers live in `frontend/assets/js/api.js` (`apiGet`, `apiPost`, and `apiPostStream` for consuming SSE endpoints) — feature JS should use these rather than raw `fetch` so error handling stays consistent. LLM Quirks further splits each case into its own subfolder (`frontend/features/llm-quirks/<case-id>/`) driven by the same case IDs as the backend registry.

**Streaming**: SSE is used only by LLM Quirks, and only for cases with `streaming=True` (currently just fox-chicken-grain — reserved for answers slow enough that a blank wait is bad UX). Backend side: a generator yields `data: {...}\n\n` lines via `StreamingResponse`; each prompt variant runs on its own thread against a shared queue (the openai client is blocking), so variants stream concurrently rather than one after another. Frontend side: `apiPostStream` in `api.js` parses that SSE framing back into JSON messages. Token Efficiency does *not* use SSE — its two pipelines (chained vs. single-shot) are run concurrently with `ThreadPoolExecutor(max_workers=2)` instead, so the wait is the slower call, not the sum of both.

**Adding an LLM Quirks case**: append one `CaseDefinition` to `CASES` in `backend/app/features/llm_quirks/cases.py` — router, schemas, and service are all driven off that registry, no other backend file needs to change. Set `streaming=True` only if the answer is slow enough (long chain-of-thought) that a blank wait would be bad UX. Set `expected` on a variant only when there's one unambiguous correct answer (enables the `matches_expected` check).

## Deployment

Deployed on Oracle Cloud (see `CONTEXT-deploy-oracle.md` for full details: instance info, systemd unit, SELinux gotcha, firewall/security-list rules). Key points:
- Live at `http://134.98.154.12:8001/`, same VM as `rag-prototype` but a separate systemd service/port.
- Committing/pushing to GitHub is always fine without asking; actually SSHing in to restart the live service (`~/llm-playground/deploy-oracle.sh` on the box) is a separate, explicitly-confirmed step every time.
- No auth/rate limiting on the API endpoints and no TLS — acceptable for a portfolio demo, not for anything sensitive.
