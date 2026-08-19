"""The router step: classifies a customer message into one of the department
categories via structured output.

Unlike the rest of this app - which talks to Mistral through the shared
`openai`-based `app.llm_client` - this feature uses LangChain
(`langchain-mistralai`'s `ChatMistralAI` + `.with_structured_output()`),
matching the stack used in the `chatagent` repo. LangChain is deliberately
scoped to this one feature rather than folded into `app.llm_client`, so that
shared, `openai`-specific module stays untouched for every other feature.
"""

from functools import lru_cache

from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from app.config import get_settings

from .schemas import Department, DepartmentInfo

# Single source of truth for the department descriptions - both the prompt
# below and the `GET /departments` endpoint (so the frontend can show users
# the full set of possible outputs up front) are built from this list.
DEPARTMENTS: list[DepartmentInfo] = [
    DepartmentInfo(code="BILLING", description="Charges, refunds, payment failures, fees, billing discrepancies."),
    DepartmentInfo(
        code="RETURNS",
        description="Return or exchange requests, damaged or wrong items, return policy questions.",
    ),
    DepartmentInfo(
        code="TECHNICAL_SUPPORT",
        description="Login issues, password resets, site/app errors, checkout bugs.",
    ),
    DepartmentInfo(code="ORDER_STATUS", description="Where an order or delivery is, shipping timing."),
    DepartmentInfo(
        code="PRODUCT_INQUIRY",
        description="Product availability, comparisons, compatibility, pricing questions.",
    ),
    DepartmentInfo(
        code="ACCOUNT_MANAGEMENT",
        description="Account settings, subscriptions, updating address or payment method.",
    ),
    DepartmentInfo(
        code="ESCALATION",
        description=(
            "An angry or frustrated customer, an explicit request for a manager, or a message "
            "that doesn't clearly fit any department above."
        ),
    ),
]

ROUTER_SYSTEM_PROMPT = (
    "You are a customer support routing assistant. Read the customer's message and decide "
    "which department should handle it.\n\nDepartments:\n"
    + "\n".join(f"- {d.code}: {d.description}" for d in DEPARTMENTS)
    + "\n\nAlways pick exactly one department. Only use ESCALATION when nothing else fits, or "
    "the customer is clearly upset and asking to be escalated. Briefly explain your reasoning."
)


class RouterOutput(BaseModel):
    department: Department
    reasoning: str


@lru_cache
def _classifier():
    """Cached ChatMistralAI instance wrapped with structured output, so the
    model/client is only built once per process (mirrors `get_client()` in
    `app/llm_client.py`).
    """
    settings = get_settings()
    llm = ChatMistralAI(
        model=settings.mistral_chat_model,
        temperature=0,
        api_key=settings.mistral_api_key,
    )
    return llm.with_structured_output(RouterOutput)


def classify(message: str) -> RouterOutput:
    return _classifier().invoke([("system", ROUTER_SYSTEM_PROMPT), ("user", message)])
