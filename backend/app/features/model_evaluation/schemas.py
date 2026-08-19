from typing import Literal

from pydantic import BaseModel, Field

# The 7 departments the router step can return. ESCALATION is not a fallback
# bolted on after the fact - it's one of the model's normal outputs, used
# when a message doesn't clearly belong to any of the other 6.
Department = Literal[
    "BILLING",
    "RETURNS",
    "TECHNICAL_SUPPORT",
    "ORDER_STATUS",
    "PRODUCT_INQUIRY",
    "ACCOUNT_MANAGEMENT",
    "ESCALATION",
]


class DepartmentInfo(BaseModel):
    """One department the router can pick, shown to the user up front so
    they know the full set of possible outputs before they try anything.
    """

    code: Department
    description: str


class ExampleMessage(BaseModel):
    """One example customer message for the "choose an example" dropdown."""

    message: str
    complexity: str


class ClassifyRequest(BaseModel):
    message: str = Field(min_length=1)


class ClassifyResponse(BaseModel):
    department: Department
    reasoning: str


class RunStatus(BaseModel):
    """Progress/result of the background test-suite run against Phoenix.
    Polled by the frontend after `POST /run-tests` kicks a run off.
    """

    status: Literal["idle", "running", "done", "error"]
    completed: int
    total: int
    accuracy: float | None = None
    error: str | None = None


class PhoenixLinkResponse(BaseModel):
    """A standing link to this feature's live activity in Phoenix - shown
    from page load, independent of whether a test run has ever been kicked
    off, so the user can see current accuracy without running anything.
    """

    url: str
