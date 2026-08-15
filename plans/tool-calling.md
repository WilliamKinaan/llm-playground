# Tool Calling — Feature Plan

## Context

Fourth top-level feature for `llm-playground` (sibling to Content Moderation, LLM
Quirks, and Token Efficiency), demonstrating LLM tool/function calling — the same
capability Mistral calls "tools" and OpenAI calls "functions" (identical JSON shape,
since Mistral exposes an OpenAI-compatible API). Reference for the request/response
shape: `~/Documents/ai/openai/tools.py` — build a
`tools=[{"type":"function","function":{name,description,parameters}}]` list, send one
chat completion, inspect `response.choices[0].message.tool_calls`, execute each call,
append `role:"tool"` messages, then a second completion for the final answer.

Unlike that aspiration script (real, hardcoded Python functions behind each tool), this
feature lets the **user define their own functions live in the browser** — name,
description, parameters, and a fixed mock return value — with no real code execution.

Agreed with user before planning:
1. **Tool execution = user-typed static mock response.** When the model calls a
   function, the backend returns the user's mock text verbatim as the tool result — no
   argument interpolation, no second LLM call to fabricate a result, no real code
   execution (keeps this safe: no arbitrary-code-execution risk from user input).
2. **Parameters UI = guided row-based builder**, not a raw JSON-Schema textarea. The
   user adds parameter rows (name, type, description, required, optional enum values);
   the **backend** assembles the actual JSON Schema from that structured list — single
   source of truth for that shape, consistent with this repo's habit of keeping such
   logic server-side.

Naming: backend slice `backend/app/features/tool_calling/` (underscore, importable —
matches `token_efficiency`); frontend folder `frontend/features/tool-calling/` (hyphen —
matches `token-efficiency`, `llm-quirks`); route prefix `/api/tool-calling`; UI title
**"Tool Calling"**, with a one-line blurb noting the Mistral/OpenAI naming difference.

## Backend

- **`backend/app/llm_client.py`**: extend `run_chat`, don't add a new function — it
  already takes a full message list and returns usage, and tool support is an additive,
  optional capability on the same call shape.
  - Add a `ToolCall` frozen dataclass: `id: str`, `name: str`, `arguments: str` (raw
    JSON string as returned by the model — not parsed here; the model can return invalid
    JSON or hallucinated parameters, so parsing/validation is `service.py`'s job).
  - Add `tool_calls: tuple[ToolCall, ...] = ()` to `ChatResult`.
  - Add `tools: list[dict[str, Any]] | None = None` param to `run_chat`. Only set
    `kwargs["tools"]` when `tools` is truthy — omit the kwarg entirely otherwise (some
    providers reject `tools: []`; keeps existing callers like `token_efficiency`
    byte-identical).
  - After the call, extract `message.tool_calls` (empty list if `None`) into the
    `ToolCall` tuple.
  - **Fix `content=message.content or ""`** when building `ChatResult` — the OpenAI SDK
    types `message.content` as nullable and it *is* `None` on tool-call turns. Normalize
    at the source rather than widening `ChatResult.content` to `str | None` (which would
    force a null-check onto the two existing callers that never hit this path).

- **New feature module `backend/app/features/tool_calling/`**:
  - `schemas.py`:
    - `ParameterDefinition` — `name` (pattern `^[A-Za-z0-9_-]{1,64}$`),
      `type: Literal["string","number","integer","boolean"]`, `description: str = ""`,
      `required: bool = False`, `enum: list[str] = []` (raw comma-split strings from the
      UI; cast to the right type in `service.py`).
    - `FunctionDefinition` — `name` (same pattern), `description: str`,
      `parameters: list[ParameterDefinition] = []` (zero params valid),
      `mock_result: str`.
    - `ToolCallingRequest` — `query: str` (non-empty), `functions: list[FunctionDefinition]
      = []` — **zero functions is deliberately allowed**, as a "no tools available"
      contrast demo, not a required minimum.
    - `ToolCallRecord` — `call_id`, `function_name` (as returned by the model — may not
      match anything defined), `arguments: dict | None` (parsed, or `None` on JSON parse
      failure), `raw_arguments: str` (always kept for display fallback),
      `matched_function: bool`, `result: str` (what was actually sent back to the
      model).
    - `ToolCallingResponse` — `tool_calls: list[ToolCallRecord]` (empty if the model
      answered directly), `final_answer: str`.
  - `service.py`:
    - `_cast_enum_value(raw, param_type)` — casts a comma-split enum string to
      `int`/`float`/`bool` per the param's declared type, falling back to the raw string
      on cast failure.
    - `_build_json_schema_parameters(params)` — builds
      `{"type":"object","properties":{...},"required":[...]}` (omit `"required"` key
      entirely when empty; zero-param function → `{"type":"object","properties":{}}`).
    - `_build_tool_schemas(functions)` — maps each `FunctionDefinition` to the
      `{"type":"function","function":{...}}` shape.
    - `run_tool_calling(query, functions) -> ToolCallingResponse`:
      1. Build `tool_schemas` (or `None` if `functions` is empty).
      2. First call: `run_chat([{"role":"user","content":query}], tools=tool_schemas)`,
         wrapped in try/except surfacing provider errors as a visible `final_answer`
         string (matches `llm_quirks/service.py`'s
         `# noqa: BLE001 - surface any provider error to the UI` pattern) rather than a
         500.
      3. If no `tool_calls` came back: return directly with `final_answer=first.content`,
         `tool_calls=[]` — mirrors the aspiration script's `else` branch.
      4. Otherwise: build the assistant `tool_calls` message, append it; for each tool
         call, `json.loads` the arguments (non-crashing — `None` + keep `raw_arguments`
         on failure), look up the function by name:
         - **Matched** → `result = defined.mock_result` verbatim (ignores parsed
           arguments entirely, per the mock-response decision).
         - **Unmatched** (model hallucinated a name) → `result = f"Unknown function:
           {tc.name}"`, `matched_function=False`. Non-crashing; this string is what's
           sent back to the model as the tool result, and the frontend flags it
           distinctly.
         Append each as a `role:"tool"` message with `tool_call_id`/`name`/`content`.
      5. **Second call deliberately omits `tools`** (unlike the aspiration script, which
         passes `tools` again) — this enforces the single-round scope boundary, not just
         documents it. No multi-round agentic loop. Wrap in try/except same as step 2.
      6. Return `ToolCallingResponse(tool_calls=records, final_answer=second.content)`.
  - `router.py` — `POST /api/tool-calling/run`
    (`APIRouter(prefix="/api/tool-calling", tags=["tool-calling"])`), delegates straight
    to `run_tool_calling`.
- **`backend/app/main.py`**: register the new router (before the `StaticFiles` mount,
  which must stay last).

## Frontend

- **`frontend/index.html`**: add a fourth "Tool Calling" card (same structure as the
  existing three), inserted after Token Efficiency.
- **`frontend/features/tool-calling/index.html` + `.js`**: follows `moderation/`
  conventions — `.panel` blocks, `hidden`-attribute toggling, `apiPost` from
  `assets/js/api.js`. Reuses existing CSS classes rather than inventing new global
  styles: `.panel`, `.hint`, `.error`, `.button-secondary`, `.badge`
  (`clear`/`flagged`), `.variant-grid`/`.variant-card`/`.variant-label`/
  `.variant-prompt`/`.variant-output`, `.explanation-panel`.
  - **Functions panel**: `#functions-list` (dynamically rendered function cards) + "Add
    function" button (`.button-secondary`). Each card: name input, description
    textarea, a `.params-list` of parameter rows (name, type `<select>`, description,
    required checkbox, enum comma-list input, remove button), an "Add parameter"
    button, and a mock-result textarea. Use **event delegation** on `#functions-list`
    for add/remove (both function cards and param rows are added/removed dynamically).
  - **Query panel**: textarea + "Run" button + error div.
  - **Results**: for each tool call, a `.variant-card` showing the function name, a
    `.badge` (`clear`/"matched" vs `flagged`/"unknown function"), the arguments
    (`JSON.stringify(record.arguments)`, or `raw_arguments + " (invalid JSON)"` on parse
    failure), and the mock result returned. If `tool_calls` is empty, show a hint ("The
    model answered directly without calling any function") instead of the grid. Always
    show `final_answer` in an `.explanation-panel`-style block.
  - **State**: DOM is the source of truth (matches `moderation.js`/`token-efficiency.js`
    — neither keeps a separate JS model object). Collect functions from the DOM at
    submit time via a `collectFunctions()` helper.
  - **Client-side validation** before submit: query non-empty; each function's `name`
    non-empty and matches the name pattern; `mock_result` non-empty. Do **not** require
    at least one function — zero is a valid, intentional demo.
  - **Seed example** (client-side only, no new backend endpoint — unlike
    `token-efficiency`'s server-owned `sample-queries`, there's no server-owned catalog
    here, the whole point is the user's own functions): on page load, pre-fill one
    editable/removable function card adapted from the aspiration script's
    `get_current_weather` (required `location` string param, optional `unit` string
    param with enum `celsius,fahrenheit`, mock result e.g. `"72°F and sunny"`) and set
    the query textarea to `"What's the weather like in Boston?"`.
- **`frontend/assets/css/style.css`**: the stylesheet currently has no rules for
  `<input type="text">` (only `textarea`/`select`/`button`), so add dark-theme input
  styling, `.param-row` grid layout (name / type / description / required / enum /
  remove), `.function-card` spacing + header flex row, `input[type="checkbox"] {
  accent-color: var(--accent); }`, and an override for the global
  `button { margin-top: 0.85rem }` on inline remove buttons inside function/param rows
  so they don't visually misalign.
- **`README.md`**: add a fourth bullet under "Currently included" describing the
  feature, matching the existing three bullets' style.
- **`CLAUDE.md`**: two edits (corrections to now-stale facts, not a new section) — add
  the fourth feature to the "What this is" list, and update the `llm_client.py`
  sentence describing `run_chat` to mention it now optionally accepts `tools` and
  returns `tool_calls`. No new "how to extend" paragraph — unlike LLM Quirks' `cases.py`
  or Token Efficiency's `catalog.py`, this feature has no server-owned data registry;
  functions are entirely user-authored per-request via the UI.

## Key decisions (so no re-derivation is needed mid-implementation)

| Question | Decision |
|---|---|
| New llm_client function vs. extend `run_chat`? | Extend `run_chat` with optional `tools` param + `tool_calls` field on `ChatResult` |
| `ChatResult.content` on tool-call turns | Normalize `None` → `""` inside `run_chat`, don't widen the type |
| Second (final-answer) call passes `tools` again? | No — deliberately dropped, enforces the single-round scope boundary |
| Unmatched function name from model | Non-crashing; `role:tool` message says "Unknown function: X"; `matched_function=False` |
| Invalid JSON in model's tool-call arguments | Non-crashing; `arguments=None`, `raw_arguments` kept, mock result still returned |
| Zero functions submitted | Allowed — deliberate "no tools available" demo; `tools` kwarg omitted entirely (not `[]`) |
| Zero parameters on a function | Allowed — `{"type":"object","properties":{}}`, no `required` key |
| Enum values for number/integer/boolean params | Cast per declared type with string fallback on cast failure |
| Client-side seed example | Yes — `get_current_weather`-style, hardcoded const in JS, fully editable/removable |

## Verification

1. Start the server: `uvicorn app.main:app --reload --app-dir backend` (from repo root).
2. Open `http://localhost:8000` — confirm the new "Tool Calling" card appears and links
   to the feature page.
3. On the feature page: confirm the seeded `get_current_weather` example is pre-filled
   and editable.
4. Click "Add function", fill in a second function (e.g. `get_world_cup_winner`), add a
   couple of parameter rows including one with enum values, then "Remove" it — confirm
   add/remove both work cleanly.
5. Run the seeded example as-is ("What's the weather like in Boston?") — confirm the
   response shows the `get_current_weather` tool call with parsed arguments, the mock
   result, and a coherent final answer referencing it.
6. Ask a question that shouldn't need any function (e.g. "What's 2+2?") with the weather
   function still defined — confirm `tool_calls` comes back empty and the "answered
   directly" hint shows.
7. Remove all functions and ask any question — confirm the zero-functions path works
   (plain chat, no `tools` kwarg sent).
8. If reproducible, try to force the model to call an undefined function name and
   confirm the "Unknown function" branch renders correctly; otherwise code-review that
   branch directly since it's hard to force deterministically.
9. Confirm the new `input[type="text"]` CSS rule doesn't regress the other three pages
   (none currently use text `<input>` elements, so this should be additive-only — spot
   check them anyway).
