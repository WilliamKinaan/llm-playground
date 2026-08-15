"""FastAPI entrypoint: registers feature API routers and serves the static
frontend. Run from the repo root with:

    uvicorn app.main:app --reload --app-dir backend
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.features.llm_quirks.router import router as llm_quirks_router
from app.features.moderation.router import router as moderation_router
from app.features.token_efficiency.router import router as token_efficiency_router
from app.features.tool_calling.router import router as tool_calling_router

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"

app = FastAPI(title="LLM Playground")

# Register feature routers here as new features are added.
app.include_router(moderation_router)
app.include_router(llm_quirks_router)
app.include_router(token_efficiency_router)
app.include_router(tool_calling_router)

# Mounted last so it only handles paths not matched by an API route above.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
