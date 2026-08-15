from typing import Literal

from pydantic import BaseModel, Field

# Mirrors OpenAI/Mistral's function-name constraints (letters, digits,
# underscores, dashes).
NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class ParameterDefinition(BaseModel):
    """One row from the frontend's guided parameter builder. `service.py`
    assembles these into an actual JSON Schema `parameters` object - this is
    just the structured shape the user fills in.
    """

    name: str = Field(pattern=NAME_PATTERN)
    type: Literal["string", "number", "integer", "boolean"]
    description: str = ""
    required: bool = False
    # Raw comma-split strings from the UI's "allowed values" field; cast to
    # match `type` when the JSON Schema is built.
    enum: list[str] = Field(default_factory=list)


class FunctionDefinition(BaseModel):
    """A function the user defined for the model to call. There is no real
    implementation behind it - `mock_result` is returned verbatim whenever
    the model calls this function, regardless of the arguments it chose.
    """

    name: str = Field(pattern=NAME_PATTERN)
    description: str
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    mock_result: str


class ToolCallingRequest(BaseModel):
    query: str = Field(min_length=1)
    # Zero functions is allowed on purpose - it's a valid "no tools
    # available" demo, not a required minimum.
    functions: list[FunctionDefinition] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    """One function call the model made, and what it got back."""

    call_id: str
    function_name: str  # as returned by the model - may not match anything defined
    arguments: dict | None  # parsed, or None if the model's JSON didn't parse
    raw_arguments: str  # always kept, so the UI has something to show either way
    matched_function: bool
    result: str  # what was actually sent back to the model as the tool result


class ToolCallingResponse(BaseModel):
    tool_calls: list[ToolCallRecord]  # empty if the model answered directly
    final_answer: str
