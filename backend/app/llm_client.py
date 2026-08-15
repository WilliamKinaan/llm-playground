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

    response = client.chat.completions.create(**kwargs)
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
