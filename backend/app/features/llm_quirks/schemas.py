from pydantic import BaseModel


class CaseSummary(BaseModel):
    """One row on the LLM Quirks index page."""

    id: str
    title: str
    teaser: str


class VariantPrompt(BaseModel):
    """A variant's prompt, without its (not-yet-run) output."""

    label: str
    prompt: str


class CaseDetail(BaseModel):
    """Everything a case page needs before the user clicks Go."""

    id: str
    title: str
    description: str
    variants: list[VariantPrompt]
    explanation: str
    # Tells the frontend which endpoint/rendering path to use: the plain
    # request/response /run endpoint, or the streaming /run-stream one.
    streaming: bool


class VariantResult(BaseModel):
    """A variant's prompt plus its live output."""

    label: str
    prompt: str
    output: str
    matches_expected: bool | None = None


class RunResponse(BaseModel):
    results: list[VariantResult]
