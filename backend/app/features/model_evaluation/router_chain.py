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

from .schemas import Department

ROUTER_SYSTEM_PROMPT = """You are a customer support routing assistant. Read the \
customer's message and decide which department should handle it.

Departments:
- BILLING: charges, refunds, payment failures, fees, billing discrepancies.
- RETURNS: return or exchange requests, damaged or wrong items, return policy questions.
- TECHNICAL_SUPPORT: login issues, password resets, site/app errors, checkout bugs.
- ORDER_STATUS: where an order or delivery is, shipping timing.
- PRODUCT_INQUIRY: product availability, comparisons, compatibility, pricing questions.
- ACCOUNT_MANAGEMENT: account settings, subscriptions, updating address or payment method.
- ESCALATION: an angry or frustrated customer, an explicit request for a manager, or a \
message that doesn't clearly fit any department above.

Always pick exactly one department. Only use ESCALATION when nothing else fits, or the \
customer is clearly upset and asking to be escalated. Briefly explain your reasoning."""


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
