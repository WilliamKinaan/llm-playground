# Model Evaluation — Feature Plan

## Context

Fifth top-level feature for `llm-playground` (sibling to Content Moderation, LLM
Quirks, Token Efficiency, and Tool Calling). It's the first step ("router step") of
a planned multi-step support-ticket pipeline: classify a customer message into one
of 7 departments (`BILLING`, `RETURNS`, `TECHNICAL_SUPPORT`, `ORDER_STATUS`,
`PRODUCT_INQUIRY`, `ACCOUNT_MANAGEMENT`, `ESCALATION`), returning
`{"department": ..., "reasoning": ...}`.

Unlike every other feature (raw `openai` client against Mistral's OpenAI-compatible
endpoint via `app/llm_client.py`), this one uses **LangChain** on purpose — mirroring
the stack in `/Users/williamkinaan/Documents/ai/chatagent` (`langchain` 1.x +
`langchain-mistralai`'s `ChatMistralAI`). That repo had no router/classification
chain to copy verbatim, so the chain itself (`.with_structured_output()` over a
Pydantic schema) is new, built in that same LangChain 1.x style. LangChain is
deliberately scoped to `router_chain.py` in this one feature rather than folded into
the shared `llm_client.py`, which stays `openai`-specific for every other feature.

Test data comes from two CSVs the user provided, copied into the feature folder
as-is (kept as CSV, not transcribed into Python literals, since they're
externally-sourced tabular data — diffable/re-importable if updated):
- `test_cases.csv` (30 rows, `test_id,customer_message,expected_department,category`)
  — the known-answer suite the "Run" button executes.
- `example_messages.csv` (22 rows, trimmed from a richer source CSV down to
  `message,complexity`) — sample messages for a "choose an example" dropdown next to
  the "Try it" textarea, purely to save typing; no expected answer attached.

**Design went through three iterations:**

**v1** (initial build) logged every "Run" to **Arize Phoenix Cloud** (the user's
personal free-tier space) as a Datasets & Experiments run, and the "View in
Phoenix" link was how results/accuracy were meant to be seen — nothing was
rendered in-page.

**v2**: the user flagged the real problem with v1 before it ever went out —
Phoenix Cloud is a personal account, so a public demo's visitors would hit a login
wall clicking that link (self-hosting Phoenix without auth was also considered and
rejected: it would add a persistent container competing for RAM/CPU with the other
services already on the same Oracle VM). Fix: results moved in-page. `RunStatus`
gained a `results: list[TestCaseResult]` field populated as each test case
finishes (test id, message, expected vs. actual department, correct/incorrect),
computed by a plain sequential loop over the test cases — no longer routed through
Phoenix's `run_experiment` task callback, so the app's own progress/results never
depended on parsing Phoenix's return shape. Phoenix logging became a decoupled,
best-effort side step (`_log_to_phoenix`) that ran *after* the real results were
already known, reused them (no second LLM call), and swallowed any error so a
Phoenix outage could never fail a run. The "View in Phoenix" link itself was gated
behind a `SHOW_PHOENIX_LINK` setting (default `false`), so it was hidden on any
deployment unless explicitly opted into.

**v3** (current): once in-page results were working and confirmed to fully cover
what Phoenix was providing, the user asked to remove Phoenix entirely rather than
keep it around gated-off. Deleted: the `arize-phoenix-client` dependency (and
uninstalled from the local venv), all `phoenix_*`/`show_phoenix_link` settings,
the `/phoenix-link` endpoint, `PhoenixLinkResponse`, and all Phoenix client/dataset
logic from `service.py`. This was a pure deletion — the in-page results added in
v2 already didn't depend on any of it, so nothing else changed behavior-wise.
`PHOENIX_*` env vars were also dropped from `.env` and `.env.example`.

## Backend — current state

`backend/app/features/model_evaluation/`, same vertical-slice split as every other
feature (`router.py` / `schemas.py` / `service.py` / data files), per `CLAUDE.md`.

- **`schemas.py`**: `Department` (the 7-value `Literal`); `DepartmentInfo` (code +
  description, for `GET /departments`); `ExampleMessage` (message + complexity, for
  `GET /examples`); `ClassifyRequest`/`ClassifyResponse` (the `{department,
  reasoning}` shape); `TestCaseResult` (one row of a run's results);  `RunStatus`
  (`status`, `completed`, `total`, `accuracy`, `error`, `results: list[TestCaseResult]`).

- **`router_chain.py`**: `DEPARTMENTS: list[DepartmentInfo]` is the single source of
  truth for department descriptions — both `ROUTER_SYSTEM_PROMPT` (built by joining
  the list) and `GET /departments` are driven off it, so the prompt and what the UI
  tells users can't drift apart. `_classifier()` is an `@lru_cache`d
  `ChatMistralAI(...).with_structured_output(RouterOutput)`, mirroring
  `get_client()`'s singleton pattern in `app/llm_client.py`. `classify(message)`
  invokes it with a `system`/`user` message pair.

- **`data.py`**: parses both CSVs at import time into `TEST_CASES: list[TestCase]`
  and `EXAMPLE_MESSAGES: list[ExampleMessage]`.

- **`service.py`**:
  - `classify_message()` — wraps `router_chain.classify`, raising a 502 with the
    provider error as `detail` on failure (checked by FastAPI's default
    `{"detail": ...}` shape, which `api.js` already parses).
  - `list_departments()` / `list_example_messages()` — thin passthroughs for the
    router.
  - Background test-suite runner: module-level `_state` dict + `threading.Lock`
    (single-run-at-a-time — a second `POST /run-tests` while one is in flight just
    returns the current status). `start_run()` spawns a daemon `threading.Thread`
    running `_run_experiment()`, matching the `threading.Thread` pattern in
    `llm_quirks/service.py`. `_run_experiment()` loops `TEST_CASES` sequentially,
    calling `_classify_test_case()` per row and appending a result dict to
    `_state["results"]` (and bumping `_state["completed"]`) after each one — this is
    what gives the frontend real per-item progress on every poll. On completion,
    accuracy is computed locally as `mean(r["correct"] for r in results)`. Any
    exception sets `status="error"` with the message in `error` rather than dying
    silently in the thread.
  - `get_run_status()` reads `_state` under the lock.

- **`router.py`**: `GET /departments`, `GET /examples`, `POST /classify`,
  `POST /run-tests`, `GET /run-status` — all under `/api/model-evaluation`.

- **`backend/app/main.py`**: `model_evaluation_router` registered like the other
  four.

- **`backend/app/config.py`**: no Model Evaluation-specific settings remain — it
  reuses `mistral_chat_model`/`mistral_api_key` like every other feature.

- **`backend/requirements.txt`**: added `langchain>=1.3,<2.0` and
  `langchain-mistralai>=1.1,<2.0` (loosely pinned like `chatagent`'s
  `requirements.txt`; `langchain-core` comes in transitively). No Phoenix package.

## Frontend — current state

`frontend/features/model-evaluation/index.html` + `model-evaluation.js`, same
skeleton as every other feature page (`breadcrumb`, shared `style.css`, `api.js`
loaded before the feature script; DOM is the source of truth, no separate JS model
object).

- **Departments panel**: `#departments-list`, populated on load from
  `GET /departments`, reusing `tool-calling`'s `.template-condition-row` styling
  (a small CSS override in `style.css` widens its first column for the longer
  department codes).
- **Try it panel**: `#message-input` textarea, an example-message `<select>` +
  "Choose" button (populated from `GET /examples`; clicking "Choose" copies the
  selected message into the textarea — no auto-fill on select), and "Classify" →
  `POST /classify` → renders a department badge (`flagged` styling for
  `ESCALATION`, `clear` otherwise) + reasoning text.
- **Test suite panel**: "Run" → `POST /run-tests` (returns immediately) → polls
  `GET /run-status` every 1.5s via `setInterval` (cleared on `"done"`/`"error"`),
  updating a progress bar/count and re-rendering `#results-list` from
  `status.results` on every poll — so result cards (test id, correct/incorrect
  badge, message, expected-vs-actual) fill in live as the run progresses, not just
  at the end. Shows the final accuracy % once `status === "done"`.
- **`frontend/index.html`**: one `.feature-card` linking to
  `/features/model-evaluation/`.

## Verification

1. `pip install -r backend/requirements.txt` (LangChain deps only — no Phoenix
   package), confirm `MISTRAL_API_KEY` set in `.env`.
2. `uvicorn app.main:app --reload --app-dir backend`, open
   `http://localhost:8000/features/model-evaluation/`.
3. Departments list renders all 7 codes + descriptions; example dropdown has 22
   entries; "Choose" copies the selected message into the textarea.
4. "Classify" on a known message (e.g. "I want to speak to a manager NOW") returns
   `ESCALATION` with non-empty reasoning.
5. "Run" doesn't block the page; progress (`N / 30 complete`) and result cards fill
   in live; final state shows 30/30 and an accuracy percentage (consistently
   ~97% — 29/30 — on the current test set).
6. `GET /api/model-evaluation/phoenix-link` returns 404 (route removed); no
   `phoenix`/`arize` string appears anywhere under `backend/` or `frontend/`; no
   `PHOENIX_*` vars in `.env`/`.env.example`; `arize-phoenix-client` uninstalled
   from the local venv.
