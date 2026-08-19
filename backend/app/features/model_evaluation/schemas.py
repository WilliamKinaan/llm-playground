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


class TestCaseResult(BaseModel):
    """One test case's outcome from a "Run" - what the router actually said
    vs. what was expected, shown in-page so results don't require Phoenix
    access to see (Phoenix Cloud is a personal account, not something a
    public demo's visitors can log into).
    """

    test_id: str
    customer_message: str
    expected_department: Department
    actual_department: Department
    correct: bool
    reasoning: str


class RunStatus(BaseModel):
    """Progress/result of the background test-suite run. Polled by the
    frontend after `POST /run-tests` kicks a run off. `results` fills in
    (one entry per finished test case) as the run progresses and is complete
    once `status` is "done".
    """

    status: Literal["idle", "running", "done", "error"]
    completed: int
    total: int
    accuracy: float | None = None
    error: str | None = None
    results: list[TestCaseResult] = Field(default_factory=list)


class PhoenixLinkResponse(BaseModel):
    """A standing link to this feature's live activity in Phoenix, for the
    owner's own use - `url` is None when `show_phoenix_link` is off (the
    default for a public deployment, since Phoenix Cloud is a personal
    account visitors can't log into).
    """

    url: str | None
