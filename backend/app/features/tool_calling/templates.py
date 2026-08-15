"""Pre-built "template" functions: fixed name/description/parameter, chosen
by us, with a fixed set of condition keys. The user can only edit the value
returned per key (and the fallback), not the keys themselves. This is the
single place to add a new template - the schemas, router, and frontend
picker are all driven off `FUNCTION_TEMPLATES`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateCondition:
    key: str  # fixed - not user-editable
    default_value: str  # starting point shown in the UI; the user can edit this


@dataclass(frozen=True)
class FunctionTemplate:
    id: str  # also used as the tool name sent to the model
    name: str
    description: str
    parameter_name: str
    parameter_description: str
    conditions: list[TemplateCondition]
    default_fallback: str  # starting point for the fallback value


FUNCTION_TEMPLATES: list[FunctionTemplate] = [
    FunctionTemplate(
        id="get_current_weather",
        name="get_current_weather",
        description="Get the current weather in a given location",
        parameter_name="location",
        parameter_description="The city to get the weather for",
        conditions=[
            TemplateCondition(key="Paris", default_value="15°C and cloudy"),
            TemplateCondition(key="Amsterdam", default_value="12°C and rainy"),
            TemplateCondition(key="Boston", default_value="72°F and sunny"),
        ],
        default_fallback="No weather data for that location.",
    ),
]

_TEMPLATES_BY_ID = {t.id: t for t in FUNCTION_TEMPLATES}


def get_template_by_id(template_id: str) -> FunctionTemplate | None:
    return _TEMPLATES_BY_ID.get(template_id)
