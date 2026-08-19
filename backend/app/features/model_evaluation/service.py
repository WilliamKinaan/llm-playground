"""Model Evaluation business logic: the LangChain router chain
(`router_chain.py`) for one-off classification, plus a background runner
that executes the known-answer test suite (`data.py`) against the router and
reports every result in-page.

The run is kicked off in a daemon thread (mirrors the `threading.Thread`
pattern already used in `llm_quirks/service.py`) so `POST /run-tests` returns
immediately; the frontend polls `GET /run-status` for progress. `_state` is a
single shared dict guarded by `_lock` - simple module-level state is fine
here since this app has no auth/multi-tenancy (see CLAUDE.md) and only one
run is meant to be in flight at a time.
"""

import threading

from fastapi import HTTPException

from .data import EXAMPLE_MESSAGES, TEST_CASES
from .router_chain import DEPARTMENTS, classify as run_router_chain
from .schemas import ClassifyResponse, DepartmentInfo, ExampleMessage, RunStatus

_lock = threading.Lock()
_state: dict = {
    "status": "idle",
    "completed": 0,
    "total": len(TEST_CASES),
    "accuracy": None,
    "error": None,
    "results": [],
}


def list_departments() -> list[DepartmentInfo]:
    return DEPARTMENTS


def list_example_messages() -> list[ExampleMessage]:
    return EXAMPLE_MESSAGES


def classify_message(message: str) -> ClassifyResponse:
    try:
        result = run_router_chain(message)
    except Exception as exc:  # noqa: BLE001 - surface any provider error to the UI
        raise HTTPException(status_code=502, detail=f"error calling the model: {exc}") from exc
    return ClassifyResponse(department=result.department, reasoning=result.reasoning)


def _classify_test_case(tc) -> dict:
    result = run_router_chain(tc.customer_message)
    return {
        "test_id": tc.test_id,
        "customer_message": tc.customer_message,
        "expected_department": tc.expected_department,
        "actual_department": result.department,
        "correct": result.department == tc.expected_department,
        "reasoning": result.reasoning,
    }


def _run_experiment() -> None:
    try:
        for tc in TEST_CASES:
            row = _classify_test_case(tc)
            with _lock:
                _state["completed"] += 1
                _state["results"].append(row)

        with _lock:
            results = _state["results"]
            accuracy = sum(1 for r in results if r["correct"]) / len(results) if results else None
            _state.update(status="done", accuracy=accuracy)
    except Exception as exc:  # noqa: BLE001 - surface any failure via /run-status instead of dying silently in the thread
        with _lock:
            _state.update(status="error", error=str(exc))


def start_run() -> RunStatus:
    with _lock:
        if _state["status"] != "running":
            _state.update(
                status="running",
                completed=0,
                total=len(TEST_CASES),
                accuracy=None,
                error=None,
                results=[],
            )
            threading.Thread(target=_run_experiment, daemon=True).start()
        return RunStatus(**_state)


def get_run_status() -> RunStatus:
    with _lock:
        return RunStatus(**_state)
