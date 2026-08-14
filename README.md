# LLM Playground

A small collection of LLM feature demos, each with its own page, sharing one
FastAPI backend.

Currently included:
- **Content Moderation** — checks text against Mistral's moderation model.
- **LLM Quirks** — small, reproducible cases where a model's behavior isn't what
  you'd expect (e.g. reversing "lollipop" breaks depending on how the word is
  tokenized), run live against the model on demand.

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
