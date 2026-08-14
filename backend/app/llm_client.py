"""Shared Mistral client.

Mistral exposes an OpenAI-compatible API, so every feature reuses the same
`openai.OpenAI` client pointed at Mistral's base URL instead of constructing
its own. Add new thin helpers here (e.g. a chat-completion wrapper) as new
features need them, so the request/response shape lives in one place.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import OpenAI
from openai.types.moderation_create_response import ModerationCreateResponse

from app.config import get_settings


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


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


def run_chat(
    messages: list[dict[str, Any]],
    temperature: float = 0,
    json_mode: bool = False,
    max_tokens: int = 500,
) -> ChatResult:
    """Send a full message list (system/user turns) and return both the reply
    and the API's real token usage. Unlike `run_chat_completion` (single
    user-string prompt, no usage reported), this is for features that need
    multi-turn control and/or want to display/compare token counts.
    """
    settings = get_settings()
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": settings.mistral_chat_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    usage = response.usage
    return ChatResult(
        content=response.choices[0].message.content,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )


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
