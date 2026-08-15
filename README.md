# LLM Playground

A small collection of LLM feature demos, each with its own page, sharing one
FastAPI backend.

Currently included:
- **Content Moderation** — checks text against Mistral's moderation model.
- **LLM Quirks** — small, reproducible cases where a model's behavior isn't what
  you'd expect (e.g. reversing "lollipop" breaks depending on how the word is
  tokenized), run live against the model on demand.
- **Token Efficiency** — compares classify-then-answer (2 small calls) against
  stuffing an entire product catalog into one prompt (1 big call), showing real
  token usage from the API for both, side by side.
- **Tool Calling** — define your own tools and watch the model decide when to use
  them. Two kinds: custom (name, description, one fixed answer, no parameters) and
  template (a few pre-built lookup functions — e.g. weather by city — where you can
  only edit the value returned per case, plus a fallback).

## Structure

- `backend/` — FastAPI app. Each feature lives in its own folder under
  `backend/app/features/<name>/` (router + schemas + service), sharing a
  single Mistral client in `backend/app/llm_client.py`.
- `frontend/` — plain HTML/CSS/JS, no build step. `index.html` links out to
  one page per feature under `frontend/features/<name>/`.

## Running it

```bash
pip install -r backend/requirements.txt
cp .env.example .env   # then fill in MISTRAL_API_KEY
uvicorn app.main:app --reload --app-dir backend
```

Open http://localhost:8000
