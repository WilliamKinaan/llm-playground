"""Tool Calling business logic: turns user-defined functions into an
OpenAI-compatible `tools` schema, lets the model decide whether/what to
call, and resolves each call - either a custom function's fixed answer, or
a template function's per-key value (falling back when the model's argument
doesn't match any known key). No real code execution anywhere.

Scoped to a single round of tool-calling (matches the aspiration script this
was ported from): the second call that produces the final answer is made
without `tools`, so the model cannot request another round.
"""

import json
from collections.abc import Callable

from app.llm_client import ChatResult, run_chat
from app.rate_limiter import reserve

from .schemas import (
    CustomFunctionDefinition,
    FunctionInput,
    FunctionTemplateOut,
    TemplateConditionOut,
    TemplateFunctionInstance,
    ToolCallRecord,
    ToolCallingResponse,
)
from .templates import FUNCTION_TEMPLATES, get_template_by_id

# Resolves a call's parsed arguments to the text sent back to the model.
Resolver = Callable[[dict | None], str]


def list_function_templates() -> list[FunctionTemplateOut]:
    return [
        FunctionTemplateOut(
            id=t.id,
            name=t.name,
            description=t.description,
            parameter_name=t.parameter_name,
            parameter_description=t.parameter_description,
            conditions=[
                TemplateConditionOut(key=c.key, default_value=c.default_value) for c in t.conditions
            ],
            default_fallback=t.default_fallback,
        )
        for t in FUNCTION_TEMPLATES
    ]


def _build_tool_schema(fn: FunctionInput) -> dict:
    if isinstance(fn, CustomFunctionDefinition):
        return {
            "type": "function",
            "function": {
                "name": fn.name,
                "description": fn.description,
                "parameters": {"type": "object", "properties": {}},
            },
        }

    template = get_template_by_id(fn.template_id)
    return {
        "type": "function",
        "function": {
            "name": template.name,
            "description": template.description,
            "parameters": {
                "type": "object",
                "properties": {
                    template.parameter_name: {
                        "type": "string",
                        "description": template.parameter_description,
                        # Nudges the model to pick one of our exact keys. Not a
                        # hard guarantee across providers, so _template_resolver
                        # still normalizes and matches server-side.
                        "enum": [c.key for c in template.conditions],
                    }
                },
                "required": [template.parameter_name],
            },
        },
    }


def _custom_resolver(fn: CustomFunctionDefinition) -> Resolver:
    def resolve(_args: dict | None) -> str:
        return fn.mock_result

    return resolve


def _template_resolver(fn: TemplateFunctionInstance) -> Resolver:
    template = get_template_by_id(fn.template_id)
    normalized_values = {
        c.key.strip().casefold(): fn.values.get(c.key, c.default_value) for c in template.conditions
    }

    def resolve(args: dict | None) -> str:
        raw = (args or {}).get(template.parameter_name)
        if isinstance(raw, str):
            match = normalized_values.get(raw.strip().casefold())
            if match is not None:
                return match
        return fn.fallback_value

    return resolve


def _build_name_and_resolver(fn: FunctionInput) -> tuple[str, Resolver]:
    if isinstance(fn, CustomFunctionDefinition):
        return fn.name, _custom_resolver(fn)
    template = get_template_by_id(fn.template_id)
    return template.name, _template_resolver(fn)


def run_tool_calling(query: str, functions: list[FunctionInput]) -> ToolCallingResponse:
    # One click here makes 1 or 2 real calls (the first, and a second round
    # only if the model asked for a tool) - reserve the worst case upfront so
    # a run either fully succeeds or fails cleanly, never returning with only
    # the first half done.
    reserve(2)
    tool_schemas = [_build_tool_schema(fn) for fn in functions] or None
    resolvers_by_name = dict(_build_name_and_resolver(fn) for fn in functions)

    messages = [{"role": "user", "content": query}]

    try:
        first: ChatResult = run_chat(messages, tools=tool_schemas)
    except Exception as exc:  # noqa: BLE001 - surface any provider error to the UI
        return ToolCallingResponse(tool_calls=[], final_answer=f"(error calling the model: {exc})")

    if not first.tool_calls:
        # No tool_calls - the model answered directly, same as the
        # aspiration script's `else` branch.
        return ToolCallingResponse(tool_calls=[], final_answer=first.content)

    assistant_message = {
        "role": "assistant",
        "content": first.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in first.tool_calls
        ],
    }
    messages.append(assistant_message)

    records: list[ToolCallRecord] = []
    for tc in first.tool_calls:
        parsed_args = None
        try:
            parsed_args = json.loads(tc.arguments)
        except (json.JSONDecodeError, TypeError):
            pass  # keep parsed_args=None; raw_arguments is still recorded below

        resolver = resolvers_by_name.get(tc.name)
        if resolver is None:
            matched = False
            # Told to the model itself as the tool result, not raised as a
            # server error - the model asked for something that doesn't
            # exist, which isn't a crash, just an unmatched call.
            result_text = f"Unknown function: {tc.name}"
        else:
            matched = True
            result_text = resolver(parsed_args)

        records.append(
            ToolCallRecord(
                call_id=tc.id,
                function_name=tc.name,
                arguments=parsed_args,
                raw_arguments=tc.arguments,
                matched_function=matched,
                result=result_text,
            )
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.name,
                "content": result_text,
            }
        )

    # Deliberately no `tools` here - this is what keeps the flow to a single
    # round instead of a multi-round agentic loop. A higher max_tokens than
    # the default 500 avoids truncating an answer that references tool
    # results plus some explanation.
    try:
        second: ChatResult = run_chat(messages, tools=None, max_tokens=800)
        final_answer = second.content
    except Exception as exc:  # noqa: BLE001 - surface any provider error to the UI
        final_answer = f"(error calling the model for the final answer: {exc})"

    return ToolCallingResponse(tool_calls=records, final_answer=final_answer)
