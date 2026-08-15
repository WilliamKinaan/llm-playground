"""Tool Calling business logic: turns user-defined function definitions into
an OpenAI-compatible `tools` schema, lets the model decide whether/what to
call, and resolves each call to a fixed mock result the user supplied - no
real code execution, no argument interpolation.

Scoped to a single round of tool-calling (matches the aspiration script this
was ported from): the second call that produces the final answer is made
without `tools`, so the model cannot request another round.
"""

import json

from app.llm_client import ChatResult, run_chat

from .schemas import FunctionDefinition, ParameterDefinition, ToolCallRecord, ToolCallingResponse


def _cast_enum_value(raw: str, param_type: str):
    """Cast one comma-split enum string to match its declared JSON Schema
    type, falling back to the raw string if it doesn't parse - a value that
    silently doesn't match the type is worse than a string left as a string.
    """
    if param_type == "integer":
        try:
            return int(raw)
        except ValueError:
            return raw
    if param_type == "number":
        try:
            return float(raw)
        except ValueError:
            return raw
    if param_type == "boolean":
        return raw.strip().lower() in ("true", "1", "yes")
    return raw


def _build_json_schema_parameters(params: list[ParameterDefinition]) -> dict:
    properties: dict[str, dict] = {}
    required: list[str] = []
    for p in params:
        prop: dict = {"type": p.type}
        if p.description:
            prop["description"] = p.description
        if p.enum:
            prop["enum"] = [_cast_enum_value(v.strip(), p.type) for v in p.enum if v.strip()]
        properties[p.name] = prop
        if p.required:
            required.append(p.name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _build_tool_schemas(functions: list[FunctionDefinition]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": f.name,
                "description": f.description,
                "parameters": _build_json_schema_parameters(f.parameters),
            },
        }
        for f in functions
    ]


def run_tool_calling(query: str, functions: list[FunctionDefinition]) -> ToolCallingResponse:
    functions_by_name = {f.name: f for f in functions}
    tool_schemas = _build_tool_schemas(functions) if functions else None

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

        defined = functions_by_name.get(tc.name)
        if defined is None:
            matched = False
            # Told to the model itself as the tool result, not raised as a
            # server error - the model asked for something that doesn't
            # exist, which isn't a crash, just an unmatched call.
            result_text = f"Unknown function: {tc.name}"
        else:
            matched = True
            result_text = defined.mock_result  # verbatim, no interpolation

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
