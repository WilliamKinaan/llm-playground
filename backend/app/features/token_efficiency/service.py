"""Token Efficiency business logic: runs the chained (classify-then-answer)
and single-shot (whole catalog in one prompt) pipelines against the same
query, concurrently, and reports real token usage for both.
"""

import json
from concurrent.futures import ThreadPoolExecutor

from app.llm_client import ChatResult, run_chat
from app.rate_limiter import reserve

from .catalog import (
    ANSWER_SYSTEM_PROMPT,
    CLASSIFICATION_SYSTEM_PROMPT,
    DELIMITER,
    PRODUCTS,
    CATEGORIES,
    get_products_by_category,
)
from .schemas import (
    CatalogCategory,
    ChainedResult,
    CompareResponse,
    Product,
    SampleQuery,
    SingleShotResult,
    StepUsage,
)

NO_MATCH_MESSAGE = (
    "We don't carry that here — our catalog covers computers & laptops, "
    "smartphones & accessories, TVs & home theater systems, gaming consoles & "
    "accessories, audio equipment, and cameras & camcorders. Is there something "
    "in one of those I can help you find?"
)

SAMPLE_QUERIES = [
    SampleQuery(
        label="Multiple products + a category",
        query="Tell me about the SmartX ProPhone and the FotoSnap DSLR camera, plus your TVs",
    ),
    SampleQuery(
        label="A single, specific product",
        query="Do you have a wireless charger?",
    ),
    SampleQuery(
        label="A whole category",
        query="What laptops do you have?",
    ),
]


def list_sample_queries() -> list[SampleQuery]:
    return SAMPLE_QUERIES


def get_catalog() -> list[CatalogCategory]:
    return [
        CatalogCategory(
            name=category,
            products=[
                Product(
                    name=p["name"],
                    category=p["category"],
                    brand=p["brand"],
                    price=p["price"],
                    description=p["description"],
                )
                for p in get_products_by_category(category)
            ],
        )
        for category in CATEGORIES
    ]


def _to_step_usage(result: ChatResult) -> StepUsage:
    return StepUsage(
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
    )


def _parse_items(classification_json: str) -> list[dict]:
    try:
        return json.loads(classification_json)["items"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def _lookup_info(items: list[dict]) -> str:
    info = ""
    for item in items:
        if "products" in item:
            for name in item["products"]:
                product = PRODUCTS.get(name)
                if product:
                    info += json.dumps(product, indent=4) + "\n"
        elif "category" in item:
            for product in get_products_by_category(item["category"]):
                info += json.dumps(product, indent=4) + "\n"
    return info


def _run_chained(query: str) -> ChainedResult:
    classification_messages = [
        {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"{DELIMITER}{query}{DELIMITER}"},
    ]
    classification_result = run_chat(classification_messages, json_mode=True)
    items = _parse_items(classification_result.content)

    if not items:
        # The classification call is cheap and already tells us nothing in
        # the catalog matches — skip the second, more expensive call
        # entirely rather than asking the model to answer from nothing
        # (which tends to hallucinate instead of just saying so).
        return ChainedResult(
            classification=classification_result.content,
            classification_usage=_to_step_usage(classification_result),
            answer=NO_MATCH_MESSAGE,
            answer_usage=StepUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            total_tokens=classification_result.total_tokens,
        )

    product_info = _lookup_info(items)

    answer_messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": query},
        {"role": "user", "content": f"\nRelevant product information:\n\n{product_info}\n"},
    ]
    answer_result = run_chat(answer_messages)

    return ChainedResult(
        classification=classification_result.content,
        classification_usage=_to_step_usage(classification_result),
        answer=answer_result.content,
        answer_usage=_to_step_usage(answer_result),
        total_tokens=classification_result.total_tokens + answer_result.total_tokens,
    )


def _run_single_shot(query: str) -> SingleShotResult:
    full_catalog_text = "\n".join(json.dumps(p, indent=4) for p in PRODUCTS.values())
    system_prompt = (
        ANSWER_SYSTEM_PROMPT
        + f"\n\nHere is the full product catalog you can reference to answer questions:\n\n{full_catalog_text}\n"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]
    result = run_chat(messages)
    return SingleShotResult(answer=result.content, usage=_to_step_usage(result))


def compare(query: str) -> CompareResponse:
    # One click here fires up to 3 real calls (chained: 1-2, single-shot: 1) -
    # reserve the worst case upfront, before dispatching either pipeline, so
    # a click either fully succeeds or fails cleanly rather than coming back
    # with one pipeline's result and the other 429'd.
    reserve(3)
    # Run both pipelines at the same time so the wait is roughly the slower
    # one, not the sum of three sequential calls.
    with ThreadPoolExecutor(max_workers=2) as executor:
        chained_future = executor.submit(_run_chained, query)
        single_shot_future = executor.submit(_run_single_shot, query)
        chained = chained_future.result()
        single_shot = single_shot_future.result()

    tokens_saved = single_shot.usage.total_tokens - chained.total_tokens
    tokens_saved_pct = (
        round(tokens_saved / single_shot.usage.total_tokens * 100, 1)
        if single_shot.usage.total_tokens
        else 0.0
    )

    return CompareResponse(
        chained=chained,
        single_shot=single_shot,
        tokens_saved=tokens_saved,
        tokens_saved_pct=tokens_saved_pct,
    )
