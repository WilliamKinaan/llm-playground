"""LLM Quirks business logic: reads the case registry and, on run, calls the
shared LLM client once per variant. Kept separate from llm_client so the
client stays generic and reusable across features.
"""

import json
import queue
import threading
from collections.abc import Iterator

from app.llm_client import run_chat_completion, stream_chat_completion

from .cases import CASES, get_case_by_id
from .schemas import CaseDetail, CaseSummary, RunResponse, VariantPrompt, VariantResult


def list_cases() -> list[CaseSummary]:
    return [CaseSummary(id=c.id, title=c.title, teaser=c.teaser) for c in CASES]


def get_case(case_id: str) -> CaseDetail | None:
    case = get_case_by_id(case_id)
    if case is None:
        return None
    return CaseDetail(
        id=case.id,
        title=case.title,
        description=case.description,
        variants=[VariantPrompt(label=v.label, prompt=v.prompt) for v in case.variants],
        explanation=case.explanation,
        streaming=case.streaming,
    )


def run_case(case_id: str) -> RunResponse | None:
    case = get_case_by_id(case_id)
    if case is None:
        return None

    results = []
    for variant in case.variants:
        try:
            output = run_chat_completion(variant.prompt)
        except Exception as exc:  # noqa: BLE001 - surface any provider error to the UI
            output = f"(error calling the model: {exc})"

        matches_expected = None
        if variant.expected is not None:
            matches_expected = output.strip().lower() == variant.expected.strip().lower()

        results.append(
            VariantResult(
                label=variant.label,
                prompt=variant.prompt,
                output=output,
                matches_expected=matches_expected,
            )
        )

    return RunResponse(results=results)


def _sse(payload: dict) -> str:
    """Format one Server-Sent-Events message. See run_case_stream for the
    JSON shapes sent in `payload`.
    """
    return f"data: {json.dumps(payload)}\n\n"


def run_case_stream(case_id: str) -> Iterator[str]:
    """Run every variant of a case concurrently, streaming each variant's
    text as it's generated instead of waiting for full replies.

    Each variant runs on its own thread (the `openai` client is blocking, so
    this is what makes them run at the same time instead of one after
    another) and pushes chunks onto a shared queue; this generator just
    drains that queue and re-emits each message as one SSE `data:` line:
      {"variant": <index>, "type": "delta", "text": "..."}   - a chunk of text
      {"variant": <index>, "type": "error", "text": "..."}   - that variant failed
      {"variant": <index>, "type": "done"}                    - that variant finished
      {"type": "complete"}                                     - every variant is done
    """
    case = get_case_by_id(case_id)
    if case is None:
        yield _sse({"type": "error", "text": f"Unknown case '{case_id}'"})
        return

    messages: queue.Queue = queue.Queue()

    def worker(index: int, prompt: str) -> None:
        try:
            for delta in stream_chat_completion(prompt):
                messages.put({"variant": index, "type": "delta", "text": delta})
        except Exception as exc:  # noqa: BLE001 - surface any provider error to the UI
            messages.put({"variant": index, "type": "error", "text": str(exc)})
        finally:
            messages.put({"variant": index, "type": "done"})

    threads = [
        threading.Thread(target=worker, args=(i, variant.prompt), daemon=True)
        for i, variant in enumerate(case.variants)
    ]
    for thread in threads:
        thread.start()

    remaining = len(threads)
    while remaining > 0:
        message = messages.get()
        yield _sse(message)
        if message["type"] == "done":
            remaining -= 1

    yield _sse({"type": "complete"})
