"""FastAPI entrypoint: registers feature API routers and serves the static
frontend. Run from the repo root with:

    uvicorn app.main:app --reload --app-dir backend
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import rate_limiter
from app.config import get_settings
from app.features.llm_quirks.router import router as llm_quirks_router
from app.features.model_evaluation.router import router as model_evaluation_router
from app.features.moderation.router import router as moderation_router
from app.features.token_efficiency.router import router as token_efficiency_router
from app.features.tool_calling.router import router as tool_calling_router
from app.rate_limiter import RateLimitExceeded

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"

app = FastAPI(title="LLM Playground")

# Register feature routers here as new features are added.
app.include_router(moderation_router)
app.include_router(llm_quirks_router)
app.include_router(token_efficiency_router)
app.include_router(tool_calling_router)
app.include_router(model_evaluation_router)


@app.get("/api/rate-limit/status")
def rate_limit_status() -> dict:
    """Read-only snapshot of the in-memory rate limiter (app/rate_limiter.py) -
    doesn't consume any budget. Called once by the frontend on page load to
    seed the rate-limit badge before the user's first action; every response
    after that carries the same numbers via the X-RateLimit-* headers added
    below, so the frontend never needs to poll this.
    """
    remaining, reset_in = rate_limiter.status()
    settings = get_settings()
    return {
        "remaining": remaining,
        "reset_in": max(0, round(reset_in)),
        "limit": settings.rate_limit_max_requests,
        "window_seconds": settings.rate_limit_window_seconds,
    }


@app.exception_handler(RateLimitExceeded)
def handle_rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": str(exc)})


@app.middleware("http")
async def add_rate_limit_headers(request: Request, call_next):
    """Stamp the current rate-limit snapshot onto every response (success or
    429 alike - the exception handler above runs before this middleware sees
    the response), so the frontend badge updates for free off responses it
    was already going to receive, with no separate polling needed.
    """
    response = await call_next(request)
    remaining, reset_in = rate_limiter.status()
    reset_seconds = max(0, round(reset_in))
    settings = get_settings()
    response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_max_requests)
    response.headers["X-RateLimit-Window-Seconds"] = str(settings.rate_limit_window_seconds)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_seconds)
    if response.status_code == 429:
        response.headers["Retry-After"] = str(max(1, reset_seconds))
    return response


# Mounted last so it only handles paths not matched by an API route above.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
