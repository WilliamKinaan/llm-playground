"""Shared Mistral client.

Mistral exposes an OpenAI-compatible API, so every feature reuses the same
`openai.OpenAI` client pointed at Mistral's base URL instead of constructing
its own. Add new thin helpers here (e.g. a chat-completion wrapper) as new
features need them, so the request/response shape lives in one place.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, NoReturn

import openai
from openai import OpenAI
from openai.types.moderation_create_response import ModerationCreateResponse

from app.config import get_settings
from app.rate_limiter import RateLimitExceeded


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as returned by the model - not parsed here, since
    # the model can return invalid JSON or hallucinated parameters; callers that need
    # tool calling own that validation


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tool_calls: tuple[ToolCall, ...] = ()


@lru_cache
def get_client() -> OpenAI:
    """Return a cached OpenAI-compatible client configured for Mistral.

    `max_retries=0`: the SDK defaults to 2 silent retries on failures
    (including 429s), which would both make our own request count
    (app.rate_limiter) inaccurate - one logical call could be up to 3 real
    requests against the shared quota - and delay surfacing a real
    provider-side rate limit to the caller.
    """
    settings = get_settings()
    return OpenAI(
        base_url=settings.mistral_base_url, api_key=settings.mistral_api_key, max_retries=0
    )


def _raise_rate_limit_exceeded(exc: openai.RateLimitError) -> NoReturn:
    """Translate a real Mistral-side 429 into our own RateLimitExceeded, the
    same exception `app.rate_limiter.reserve()` raises for our local guard -
    so callers/the frontend see one consistent error either way. This is our
    local budget's blind spot showing up: it only sees this process's
    traffic, so Mistral can still throttle even when our own counter thought
    there was room (e.g. another app sharing this key used it up).
    """
    retry_after = None
    response = getattr(exc, "response", None)
    if response is not None:
        header = response.headers.get("retry-after")
        if header:
            try:
                retry_after = float(header)
            except ValueError:
                retry_after = None
    if retry_after is None:
        retry_after = get_settings().rate_limit_window_seconds
    raise RateLimitExceeded(retry_after, remaining=0) from exc


def run_moderation(text: str) -> ModerationCreateResponse:
    """Call Mistral's moderation endpoint for a single piece of text."""
    settings = get_settings()
    client = get_client()
    try:
        return client.moderations.create(model=settings.mistral_moderation_model, input=text)
    except openai.RateLimitError as exc:
        _raise_rate_limit_exceeded(exc)


def run_chat_completion(prompt: str, temperature: float = 0) -> str:
    """Send a single user prompt to the chat model and return its reply text."""
    settings = get_settings()
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=settings.mistral_chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
    except openai.RateLimitError as exc:
        _raise_rate_limit_exceeded(exc)
    return response.choices[0].message.content


def run_chat(
    messages: list[dict[str, Any]],
    temperature: float = 0,
    json_mode: bool = False,
    max_tokens: int = 500,
    tools: list[dict[str, Any]] | None = None,
) -> ChatResult:
    """Send a full message list (system/user turns) and return both the reply
    and the API's real token usage. Unlike `run_chat_completion` (single
    user-string prompt, no usage reported), this is for features that need
    multi-turn control and/or want to display/compare token counts.

    Pass `tools` (OpenAI-compatible `[{"type": "function", "function": {...}}]`
    shape) to let the model call functions; any calls it makes come back on
    `ChatResult.tool_calls` instead of `content` (which the API leaves empty
    on a tool-call turn - normalized to `""` here rather than `None`).
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
    if tools:
        kwargs["tools"] = tools

    try:
        response = client.chat.completions.create(**kwargs)
    except openai.RateLimitError as exc:
        _raise_rate_limit_exceeded(exc)
    usage = response.usage
    message = response.choices[0].message
    tool_calls = tuple(
        ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
        for tc in (message.tool_calls or [])
    )
    return ChatResult(
        content=message.content or "",
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        tool_calls=tool_calls,
    )


def stream_chat_completion(prompt: str, temperature: float = 0):
    """Send a single user prompt to the chat model, yielding text as it
    arrives instead of waiting for the full reply. For prompts that take a
    long time to finish (long chain-of-thought answers), this is what lets a
    caller show progress instead of a blank wait.
    """
    settings = get_settings()
    client = get_client()
    try:
        stream = client.chat.completions.create(
            model=settings.mistral_chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            stream=True,
        )
    except openai.RateLimitError as exc:
        _raise_rate_limit_exceeded(exc)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
