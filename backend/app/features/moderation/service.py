"""Moderation business logic: calls the shared LLM client and shapes the
result into the response schema the frontend renders. Keeping this shaping
here (rather than in the router or the client) means the router stays a thin
transport layer and llm_client stays generic/reusable across features.
"""

from app.llm_client import run_moderation

from .schemas import CategoryResult, ModerationResponse


def check_moderation(text: str) -> ModerationResponse:
    response = run_moderation(text)
    result = response.results[0]

    categories = result.categories.model_dump()
    scores = result.category_scores.model_dump()

    # The OpenAI-compatible shim reports both the legacy OpenAI category set
    # and Mistral's own set on every response; whichever set doesn't apply to
    # this model comes back as `None` and is skipped here.
    category_results = [
        CategoryResult(name=name, flagged=bool(flagged), score=float(scores[name]))
        for name, flagged in categories.items()
        if flagged is not None and scores.get(name) is not None
    ]
    category_results.sort(key=lambda c: c.score, reverse=True)

    # `result.flagged` isn't reliably populated by the OpenAI-compat shim for
    # Mistral's own category set, so derive it from the categories we kept.
    flagged = any(category.flagged for category in category_results)

    return ModerationResponse(flagged=flagged, categories=category_results)
