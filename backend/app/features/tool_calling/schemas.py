from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from .templates import get_template_by_id

# Mirrors OpenAI/Mistral's function-name constraints (letters, digits,
# underscores, dashes).
NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class CustomFunctionDefinition(BaseModel):
    """A fully user-authored function: name, description, and one fixed
    answer. Deliberately parameter-less - a single static answer only makes
    sense when there's no argument for it to (incorrectly) ignore. Functions
    whose answer should vary by argument are template functions instead.
    """

    kind: Literal["custom"] = "custom"
    name: str = Field(pattern=NAME_PATTERN)
    description: str
    mock_result: str


class TemplateFunctionInstance(BaseModel):
    """One of our pre-built functions (name/description/parameter/condition
    keys fixed by `templates.py`), with the user's edited values. The user
    can change what each key returns, not the keys themselves.
    """

    kind: Literal["template"] = "template"
    template_id: str
    values: dict[str, str] = Field(default_factory=dict)  # condition key -> value
    fallback_value: str = ""


FunctionInput = Annotated[
    CustomFunctionDefinition | TemplateFunctionInstance,
    Field(discriminator="kind"),
]


class ToolCallingRequest(BaseModel):
    query: str = Field(min_length=1)
    # Zero functions is allowed on purpose - it's a valid "no tools
    # available" demo, not a required minimum.
    functions: list[FunctionInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_functions(self) -> "ToolCallingRequest":
        seen_names: set[str] = set()
        for fn in self.functions:
            if fn.kind == "custom":
                name = fn.name
            else:
                template = get_template_by_id(fn.template_id)
                if template is None:
                    raise ValueError(f"Unknown template_id: {fn.template_id}")
                name = template.name
            if name in seen_names:
                raise ValueError(f"Duplicate function name: {name}")
            seen_names.add(name)
        return self


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


class TemplateConditionOut(BaseModel):
    key: str
    default_value: str


class FunctionTemplateOut(BaseModel):
    """What the frontend needs to render the "Add template" picker and
    pre-fill a template card's editable fields.
    """

    id: str
    name: str
    description: str
    parameter_name: str
    parameter_description: str
    conditions: list[TemplateConditionOut]
    default_fallback: str
