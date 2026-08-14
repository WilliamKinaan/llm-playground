"""Shared Mistral client.

Mistral exposes an OpenAI-compatible API, so every feature reuses the same
`openai.OpenAI` client pointed at Mistral's base URL instead of constructing
its own. Add new thin helpers here (e.g. a chat-completion wrapper) as new
features need them, so the request/response shape lives in one place.
"""

from functools import lru_cache

from openai import OpenAI
from openai.types.moderation_create_response import ModerationCreateResponse

from app.config import get_settings


@lru_cache
def get_client() -> OpenAI:
    """Return a cached OpenAI-compatible client configured for Mistral."""
    settings = get_settings()
    return OpenAI(base_url=settings.mistral_base_url, api_key=settings.mistral_api_key)


def run_moderation(text: str) -> ModerationCreateResponse:
    """Call Mistral's moderation endpoint for a single piece of text."""
    settings = get_settings()
    client = get_client()
    return client.moderations.create(model=settings.mistral_moderation_model, input=text)


def run_chat_completion(prompt: str, temperature: float = 0) -> str:
    """Send a single user prompt to the chat model and return its reply text."""
    settings = get_settings()
    client = get_client()
    response = client.chat.completions.create(
        model=settings.mistral_chat_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content


def stream_chat_completion(prompt: str, temperature: float = 0):
    """Send a single user prompt to the chat model, yielding text as it
    arrives instead of waiting for the full reply. For prompts that take a
    long time to finish (long chain-of-thought answers), this is what lets a
    caller show progress instead of a blank wait.
    """
    settings = get_settings()
    client = get_client()
    stream = client.chat.completions.create(
        model=settings.mistral_chat_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
