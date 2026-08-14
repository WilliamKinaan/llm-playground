# LLM Playground — Initial Setup Plan

## Context
Starting a new prototype, `llm-playground`, in an empty git repo. It will grow into a
collection of small, independent LLM-feature demos (moderation is the first; more will
be added later), each reachable from a landing page. Backend is Python, calling Mistral's
API (OpenAI-compatible client) using the free `ministral-8b-latest` chat model and
`mistral-moderation-latest` for moderation — the pattern is already sketched in
`/Users/williamkinaan/Documents/ai/openai/moderation.py` (not part of this repo).
The priority is a clean, modular structure so each new feature (planned: more beyond
moderation) can be dropped in without restructuring the app, and a real API key must
never be hardcoded/committed.

Decisions confirmed with user: FastAPI backend, single process serves both the API and
the static frontend, and the moderation results UI shows a polished per-category
breakdown (not raw JSON).

## Repo layout
```
llm-playground/
  backend/
    app/
      main.py                 # FastAPI app: mounts /frontend static files, includes feature routers
      config.py                # Settings (pydantic-settings): MISTRAL_API_KEY, model names, read from .env
      llm_client.py            # Shared Mistral client factory + thin helpers (chat completion, moderation call)
      features/
        moderation/
          router.py            # POST /api/moderation/check
          schemas.py           # Pydantic request/response models
          service.py           # Business logic: calls llm_client, shapes result for the UI
    requirements.txt
    .env.example               # documents required env vars, no real secrets
  frontend/
    index.html                 # Landing page: title, one card/link per feature
    assets/
      css/style.css            # Shared site-wide styling (nav/cards/layout), reused by every feature page
      js/api.js                 # Shared fetch() helper (base URL, error handling) reused by every feature page
    features/
      moderation/
        index.html              # Moderation demo page (text input, submit, results panel)
        moderation.js            # Calls /api/moderation/check, renders flagged badge + category score bars
  plans/
    initialsetupplan.md         # This plan, committed to the repo per user's request
  .gitignore                    # .env, __pycache__, venv, etc.
  README.md                     # Minimal: what it is, how to run it (no "demonstrates my AI skills" framing)
```

## Backend design
- **`config.py`**: loads `MISTRAL_API_KEY` (required, no default/fallback value) and
  `MISTRAL_CHAT_MODEL` / `MISTRAL_MODERATION_MODEL` (defaulted, overridable) from `.env`
  via `pydantic-settings`. `.env` is gitignored; `.env.example` documents the keys.
- **`llm_client.py`**: single place that builds the OpenAI-compatible client pointed at
  `https://api.mistral.ai/v1`, mirroring the sample script. Exposes small reusable
  functions (e.g. `get_client()`, `run_moderation(text)`) so future features (chat-based
  ones) reuse the same client construction instead of duplicating it.
- **Feature module pattern** (`features/moderation/`): router + schemas + service, kept
  separate so a future feature is just a new sibling folder following the same shape,
  registered with one line in `main.py`. Router only talks to `service.py`; `service.py`
  only talks to `llm_client.py` — keeps the moderation-specific shaping logic (flagged
  categories, score formatting) out of the client and the transport layer.
- **`main.py`**: creates the FastAPI app, includes the moderation router under `/api`,
  and mounts `frontend/` as static files so the whole thing runs with one
  `uvicorn backend.app.main:app` command.

## Frontend design
- Plain HTML/CSS/JS (no build step), consistent with a prototype meant to be read and
  demoed quickly.
- `assets/css/style.css` and `assets/js/api.js` are shared across the landing page and
  every feature page so new feature pages stay small and consistent.
- `index.html` lists feature cards with links; only "Content Moderation" for now, styled
  so adding more cards later is trivial.
- Moderation page: textarea + submit button, calls the API via `api.js`, then renders a
  flagged/clear badge and a bar/percentage per moderation category returned by Mistral.

## Verification
1. `pip install -r backend/requirements.txt`, set `MISTRAL_API_KEY` in `.env`.
2. Run `uvicorn app.main:app --reload --app-dir backend` from the repo root.
3. Open `http://localhost:8000/` → landing page loads, link to moderation page works.
4. On the moderation page, submit a clearly benign text and a clearly flaggable text
   (e.g. text similar to the sample script's example) and confirm the UI shows the
   correct flagged/clear state and per-category scores.
5. `curl -X POST http://localhost:8000/api/moderation/check -H "Content-Type: application/json" -d '{"text":"..."}'` to confirm the API works independent of the UI.
6. Confirm `.env` is not tracked by git (`git status` after running).
