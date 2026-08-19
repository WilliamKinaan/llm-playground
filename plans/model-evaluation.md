# Model Evaluation feature (router step) + Phoenix Cloud eval tracking

## Context

This adds a new feature, **Model Evaluation**, to `llm-playground`. It's the first step ("router step") of a planned multi-step pipeline: classify a customer message into one of 7 departments (`BILLING`, `RETURNS`, `TECHNICAL_SUPPORT`, `ORDER_STATUS`, `PRODUCT_INQUIRY`, `ACCOUNT_MANAGEMENT`, `ESCALATION`), returning `{"department": ..., "reasoning": ...}`. Unlike the rest of the app (raw `openai` client against Mistral's OpenAI-compatible endpoint), this feature must use **LangChain** — mirroring the stack in `/Users/williamkinaan/Documents/ai/chatagent` (`langchain` 1.x + `langchain-mistralai`'s `ChatMistralAI`, config via `pydantic-settings`). That repo has no router/classification chain to copy verbatim, so the classification chain itself (`.with_structured_output()` over a Pydantic schema) is new, built in that same LangChain 1.x style.

The user has 30 known-answer test cases (`/Users/williamkinaan/Downloads/agentic-ai-build-your-first-agentic-ai-system-4645038-main/data/v1_test_cases.csv`, columns `test_id,customer_message,expected_department,category`). Clicking "Run" should execute all of them against the router in the background (non-blocking, UI polls for progress) and log results to **Arize Phoenix** so accuracy can be tracked run-over-run. Confirmed with the user: use **Phoenix Cloud's free tier** (hosted at `app.phoenix.arize.com`) rather than self-hosting Phoenix in Docker on the Oracle VM — no extra RAM/CPU/disk footprint on the box that already runs `rag-prototype` + this app, and the free tier (~50k traces/mo, ~7-day retention) is far more than a ~30-case demo needs. The user already provided a Phoenix API key — **it goes only into `.env` (gitignored) as `PHOENIX_API_KEY`, never into committed code, the plan, or any file under version control.**

Phoenix's **Datasets & Experiments** feature is the right primitive for "accuracy over time": upload the 30 test cases once as a Dataset, then each "Run" click calls `run_experiment(dataset, task=..., evaluators=[...])` under a fresh timestamped experiment name. Phoenix's UI lists every experiment run against that dataset with its evaluator score, in chronological order — exactly "accuracy by time" — with no custom charting code needed on our side.

## Backend

### New dependencies (`backend/requirements.txt`)
Add, loosely pinned like `chatagent`'s `requirements.txt`:
```
langchain>=1.3,<2.0
langchain-mistralai>=1.1,<2.0
arize-phoenix-client
```
(`langchain-core` comes in transitively.) `arize-phoenix-client` is the lightweight client-only package (talks to any Phoenix instance over HTTP — cloud or self-hosted — for datasets/experiments); it does not bundle a local server, so no new process to run.

### Config (`backend/app/config.py`)
Add fields to `Settings`, following the existing `mistral_*` pattern (sane defaults where possible, required where not):
```python
phoenix_api_key: str
phoenix_base_url: str = "https://app.phoenix.arize.com/s/<space-name>"  # exact value confirmed during build from the user's Phoenix space
phoenix_project_name: str = "model-evaluation"
```
Update `.env.example` with `PHOENIX_API_KEY=` (placeholder) and a comment pointing at `app.phoenix.arize.com`. The real key the user pasted goes straight into their local `.env`, never echoed elsewhere.

### New feature: `backend/app/features/model_evaluation/`
Mirrors the `tool_calling` feature's file split (`router.py` / `schemas.py` / `service.py` / data file), per `CLAUDE.md`'s vertical-slice convention.

- **`schemas.py`** — `Department = Literal["BILLING","RETURNS","TECHNICAL_SUPPORT","ORDER_STATUS","PRODUCT_INQUIRY","ACCOUNT_MANAGEMENT","ESCALATION"]`; `ClassifyRequest {message: str}`; `ClassifyResponse {department: Department, reasoning: str}` (matches the required `{"department": ..., "reasoning": ...}` shape exactly); `RunStatus {status: Literal["idle","running","done","error"], completed: int, total: int, accuracy: float | None, experiment_url: str | None, error: str | None}`.

- **`router_chain.py`** — the LangChain piece, isolated here rather than in the shared `app/llm_client.py` (which is `openai`-specific and used by every other feature — keeping LangChain scoped to this one feature avoids disturbing that shared module):
  ```python
  from langchain_mistralai import ChatMistralAI
  from pydantic import BaseModel

  class RouterOutput(BaseModel):
      department: Department
      reasoning: str

  @lru_cache
  def _classifier():
      settings = get_settings()
      llm = ChatMistralAI(model=settings.mistral_chat_model, temperature=0, api_key=settings.mistral_api_key)
      return llm.with_structured_output(RouterOutput)

  def classify(message: str) -> RouterOutput:
      return _classifier().invoke([("system", ROUTER_SYSTEM_PROMPT), ("user", message)])
  ```
  `ROUTER_SYSTEM_PROMPT` lists the 6 real departments with a one-line description each, and instructs the model to return `ESCALATION` only when nothing else clearly fits.

- **`test_cases.csv`** — the user's 30 rows copied in as-is (kept as CSV, not transcribed into a Python literal, since it's externally-sourced tabular data — diffable/re-importable if the user updates it later).

- **`data.py`** — parses `test_cases.csv` at import time into `TEST_CASES: list[TestCase]` (`@dataclass(frozen=True)`: `test_id, customer_message, expected_department, category`), same "single source of truth" role as `cases.py`/`catalog.py`.

- **`service.py`**:
  - `classify_message(message: str) -> ClassifyResponse` — wraps `router_chain.classify`, same try/except-to-inline-error-string pattern as `tool_calling/service.py`, for the ad-hoc "try a prompt" panel.
  - Background experiment runner, guarded by a module-level `_STATE` dict + `threading.Lock` (single-run-at-a-time; a second `POST /run-tests` while one is in flight just returns the current status instead of double-starting):
    - `start_run()` spawns a daemon `threading.Thread` running `_run_experiment()`, mirroring the `ThreadPoolExecutor`/`threading.Thread` patterns already used in `token_efficiency` and `llm_quirks`.
    - `_run_experiment()`: gets-or-creates a Phoenix dataset named e.g. `"router-test-cases"` from `TEST_CASES` (lookup by name first so re-runs reuse the same dataset id); defines `task(example)` that calls `router_chain.classify(example.input["customer_message"])` **and increments `_STATE["completed"]` as a side effect** (this gives real per-item progress even though `run_experiment` owns the iteration — no need to reimplement it); defines `evaluator(output, example)` comparing `output.department` to `example.output["expected_department"]`, returning score `1.0`/`0.0`, label `correct`/`incorrect`; calls `phoenix.Client(...).experiments.run_experiment(dataset, task=task, evaluators=[evaluator], experiment_name=f"router-eval-{utc_timestamp}")`; on completion stores `accuracy` (mean score) and the experiment's Phoenix UI URL into `_STATE`; any exception is caught and stored in `_STATE["error"]` rather than crashing the thread.
  - `get_run_status() -> RunStatus` reads `_STATE`.

- **`router.py`**:
  ```python
  router = APIRouter(prefix="/api/model-evaluation", tags=["model-evaluation"])

  @router.post("/classify", response_model=ClassifyResponse)
  def classify(request: ClassifyRequest) -> ClassifyResponse: ...

  @router.post("/run-tests", response_model=RunStatus)
  def run_tests() -> RunStatus: ...   # starts (or no-ops onto) the background run, returns current status

  @router.get("/run-status", response_model=RunStatus)
  def run_status() -> RunStatus: ...  # polled by the frontend
  ```

### `backend/app/main.py`
Import and `app.include_router(model_evaluation_router)`, same one-line pattern as the other three features.

## Frontend

- **`frontend/features/model-evaluation/index.html` + `model-evaluation.js`** — same skeleton as `tool-calling` (`breadcrumb`, shared `style.css`, `api.js` loaded before the feature script). Two panels:
  1. **Try it**: textarea for a message + "Classify" button → `apiPost("/api/model-evaluation/classify", ...)` → renders the department as a badge and the reasoning text (mirrors the exact `{department, reasoning}` JSON shape visually).
  2. **Run test suite**: "Run" button → `apiPost("/api/model-evaluation/run-tests", {})`, then polls `apiGet("/api/model-evaluation/run-status")` every ~2s (simple `setInterval`, cleared on `"done"`/`"error"`) updating a live "`{completed} / {total}` complete" line; on `"done"` shows the resulting accuracy % and a **"View in Phoenix →"** link (`target="_blank"`) to `experiment_url`.
- **`frontend/index.html`** — add one more `.feature-card` linking to `/features/model-evaluation/`.

## Verification

1. `pip install -r backend/requirements.txt` (new LangChain + Phoenix client deps), fill `PHOENIX_API_KEY` into root `.env`, confirm `MISTRAL_API_KEY` still set.
2. `uvicorn app.main:app --reload --app-dir backend`, open `http://localhost:8000/features/model-evaluation/`.
3. "Try it" panel: submit a couple of the CSV's messages by hand (e.g. `"I want to speak to a manager NOW"`) and confirm the returned department matches the CSV's `expected_department` (`ESCALATION`) and reasoning is non-empty.
4. Click "Run" — confirm the button/UI doesn't block, progress counter advances toward 30/30, and on completion an accuracy % and a working Phoenix link appear.
5. Open the Phoenix link — confirm the dataset (`router-test-cases`, 30 examples) and the new experiment run with its per-example scores are visible in the Phoenix Cloud UI.
6. Click "Run" a second time — confirm it reuses the same dataset (doesn't duplicate it) and creates a *second* experiment entry, so the dataset's experiment list now shows two dated accuracy data points — the "accuracy over time" view.
