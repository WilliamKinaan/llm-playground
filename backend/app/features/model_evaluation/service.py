"""Model Evaluation business logic: the LangChain router chain
(`router_chain.py`) for one-off classification, plus a background runner
that executes the known-answer test suite (`data.py`) against the router and
logs the results to a Phoenix Experiment - so accuracy can be tracked
run-over-run in the Phoenix UI instead of anything we'd have to build here.

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

from .data import TEST_CASES
from .router_chain import classify as run_router_chain
from .schemas import ClassifyResponse, RunStatus

DATASET_NAME = "router-test-cases"

_lock = threading.Lock()
_state: dict = {
    "status": "idle",
    "completed": 0,
    "total": len(TEST_CASES),
    "accuracy": None,
    "experiment_url": None,
    "dataset_url": None,
    "error": None,
}


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


def _task(input: dict) -> dict:
    # Param name `input` is required by Phoenix's task-signature binding
    # (it maps the example's `input` field onto whichever of a fixed set of
    # names - input/expected/reference/metadata/example - the task asks for).
    result = run_router_chain(input["customer_message"])
    with _lock:
        _state["completed"] += 1
    return {"department": result.department, "reasoning": result.reasoning}


def _correctness(output: dict, expected: dict) -> tuple[float, str]:
    predicted = (output or {}).get("department")
    actual = (expected or {}).get("expected_department")
    is_correct = predicted == actual
    return (1.0 if is_correct else 0.0, "correct" if is_correct else "incorrect")


def _run_experiment() -> None:
    try:
        client = _phoenix_client()
        dataset = _get_or_create_dataset(client)

        experiment_name = f"router-eval-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        ran = client.experiments.run_experiment(
            dataset=dataset,
            task=_task,
            evaluators=[_correctness],
            experiment_name=experiment_name,
            print_summary=False,
        )

        # `run.result` is a single ExperimentEvaluation dict for the common
        # one-evaluator case, but the type allows a sequence too - normalize
        # so this doesn't break if another evaluator gets added later.
        evaluations = []
        for run in ran["evaluation_runs"]:
            if run.result is None:
                continue
            evaluations.extend(run.result if isinstance(run.result, list) else [run.result])
        scores = [ev["score"] for ev in evaluations if ev.get("score") is not None]
        accuracy = sum(scores) / len(scores) if scores else None
        experiment_url = client.experiments.get_experiment_url(
            dataset_id=dataset.id, experiment_id=ran["experiment_id"]
        )
        dataset_url = client.experiments.get_dataset_experiments_url(dataset_id=dataset.id)

        with _lock:
            _state.update(
                status="done",
                accuracy=accuracy,
                experiment_url=experiment_url,
                dataset_url=dataset_url,
            )
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
                experiment_url=None,
                dataset_url=None,
                error=None,
            )
            threading.Thread(target=_run_experiment, daemon=True).start()
        return RunStatus(**_state)


def get_run_status() -> RunStatus:
    with _lock:
        return RunStatus(**_state)
