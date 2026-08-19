"""Model Evaluation business logic: the LangChain router chain
(`router_chain.py`) for one-off classification, plus a background runner
that executes the known-answer test suite (`data.py`) against the router.

Results are shown in-page (see `TestCaseResult` in schemas.py) rather than
requiring Phoenix access to view - Phoenix Cloud is a personal account, and
a public deployment's visitors can't log into it. Runs are still logged to
Phoenix as an Experiment for the owner's own private use (accuracy
run-over-run in the Phoenix UI), but the app never depends on Phoenix to
show a visitor their own results.

The run is kicked off in a daemon thread (mirrors the `threading.Thread`
pattern already used in `llm_quirks/service.py`) so `POST /run-tests` returns
immediately; the frontend polls `GET /run-status` for progress. `_state` is a
single shared dict guarded by `_lock` - simple module-level state is fine
here since this app has no auth/multi-tenancy (see CLAUDE.md) and only one
run is meant to be in flight at a time.
"""

import threading
from datetime import datetime, timezone

from fastapi import HTTPException
from phoenix.client import Client as PhoenixClient

from app.config import get_settings

from .data import EXAMPLE_MESSAGES, TEST_CASES
from .router_chain import DEPARTMENTS, classify as run_router_chain
from .schemas import ClassifyResponse, DepartmentInfo, ExampleMessage, RunStatus

DATASET_NAME = "router-test-cases"

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


def get_phoenix_spans_url() -> str | None:
    """A standing link to this feature's live activity in Phoenix, for the
    owner's own use. Returns None (hidden) unless SHOW_PHOENIX_LINK is set -
    Phoenix Cloud is a personal account, so this stays off by default on any
    deployment a visitor other than the owner might reach.
    """
    settings = get_settings()
    if not settings.show_phoenix_link:
        return None
    return f"{settings.phoenix_base_url}/projects/{settings.phoenix_project_id}/spans?timeRangeKey=1d"


def classify_message(message: str) -> ClassifyResponse:
    try:
        result = run_router_chain(message)
    except Exception as exc:  # noqa: BLE001 - surface any provider error to the UI
        raise HTTPException(status_code=502, detail=f"error calling the model: {exc}") from exc
    return ClassifyResponse(department=result.department, reasoning=result.reasoning)


def _phoenix_client() -> PhoenixClient:
    settings = get_settings()
    return PhoenixClient(base_url=settings.phoenix_base_url, api_key=settings.phoenix_api_key)


def _get_or_create_dataset(client: PhoenixClient):
    try:
        return client.datasets.get_dataset(dataset=DATASET_NAME)
    except Exception:  # noqa: BLE001 - not found (or any lookup failure) means create it
        examples = [
            {
                "input": {"customer_message": tc.customer_message},
                "output": {"expected_department": tc.expected_department},
                "metadata": {"test_id": tc.test_id, "category": tc.category},
            }
            for tc in TEST_CASES
        ]
        return client.datasets.create_dataset(
            name=DATASET_NAME,
            examples=examples,
            dataset_description="Router step test cases: customer message -> expected department.",
        )


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


def _correctness(output: dict, expected: dict) -> tuple[float, str]:
    predicted = (output or {}).get("department")
    actual = (expected or {}).get("expected_department")
    is_correct = predicted == actual
    return (1.0 if is_correct else 0.0, "correct" if is_correct else "incorrect")


def _log_to_phoenix(results: list[dict]) -> None:
    """Best-effort: log the already-computed results to Phoenix as an
    Experiment, for the owner's own private run-over-run tracking there.
    Deliberately swallows any error - a Phoenix hiccup (down, rate-limited,
    misconfigured) must never take down a run whose real results (computed
    in `_run_experiment` below, independent of Phoenix) are already known
    and already visible to whoever is using the page.
    """
    try:
        client = _phoenix_client()
        dataset = _get_or_create_dataset(client)
        results_by_test_id = {r["test_id"]: r for r in results}

        def task(example):
            r = results_by_test_id[example.metadata["test_id"]]
            return {"department": r["actual_department"], "reasoning": r["reasoning"]}

        experiment_name = f"router-eval-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        client.experiments.run_experiment(
            dataset=dataset,
            task=task,
            evaluators=[_correctness],
            experiment_name=experiment_name,
            print_summary=False,
        )
    except Exception:  # noqa: BLE001 - best-effort only, see docstring
        pass


def _run_experiment() -> None:
    try:
        for tc in TEST_CASES:
            row = _classify_test_case(tc)
            with _lock:
                _state["completed"] += 1
                _state["results"].append(row)

        with _lock:
            results = list(_state["results"])
            accuracy = sum(1 for r in results if r["correct"]) / len(results) if results else None
            _state.update(status="done", accuracy=accuracy)
    except Exception as exc:  # noqa: BLE001 - surface any failure via /run-status instead of dying silently in the thread
        with _lock:
            _state.update(status="error", error=str(exc))
        return

    _log_to_phoenix(results)


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
