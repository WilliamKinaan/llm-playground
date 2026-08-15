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
feature lets the **user define their own functions live in the browser** — with no real
code execution. The design went through two iterations:

**v1** (initial build) had one function shape: arbitrary name/description/parameters
plus a single static mock result returned regardless of what arguments the model
passed. That was a gap for anything where the *result* should depend on the argument
(e.g. "weather in Paris" vs. "weather in Amsterdam" should differ, but always got the
same mock text back).

**v2** (current) splits functions into two kinds:
- **Custom** — fully user-authored (name, description, one answer), now strictly
  **parameter-less**, so the one static answer is always the right one — there's no
  argument for it to (incorrectly) ignore anymore.
- **Template** — pre-built by us, with a fixed name/description/parameter and a fixed
  set of condition keys. The user can only edit the **value** returned per key, plus a
  fallback for anything else — not the keys themselves. Currently one template ships:
  `get_current_weather(location)` with keys `Paris`, `Amsterdam`, `Boston`.

Decisions locked in for v2:
1. **Tool execution is still static, per-kind** — custom always returns its one answer;
   template looks up the model's argument against the user's edited key→value table and
   falls back if nothing matches. Still no real code execution, no LLM-simulated
   results.
2. **Template keys are fixed by us, not user-defined.** A future "user-defined
   condition table" feature (see below) would let the user build their own key→value
   list from scratch instead of only picking from a shipped template — deliberately not
   built now.
3. **Key matching**: the parameter's JSON Schema `enum` is set to the template's exact
   keys (nudges the model to pick one), *and* the server independently normalizes
   (`.strip().casefold()`) and matches against those keys before falling back — enum
   isn't a hard guarantee across providers, so this is defense-in-depth, not redundant.
4. **One instance per template.** "Add function" is two controls: "Add custom function"
   and an "Add template" dropdown limited to templates not already on the page; a
   template disappears from the dropdown once added, reappears once its card is
   removed.
5. The v1 generic parameter-builder (arbitrary name/type/description/required/enum
   rows per function) was **deleted**, not kept alongside — it became dead weight once
   custom functions can't take parameters, and templates don't need it either since
   their parameter is fixed. See "What's possible next" below for how it could return
   in a different, narrower form.

Naming: backend slice `backend/app/features/tool_calling/` (underscore, importable —
matches `token_efficiency`); frontend folder `frontend/features/tool-calling/` (hyphen —
matches `token-efficiency`, `llm-quirks`); route prefix `/api/tool-calling`; UI title
**"Tool Calling"**.

Copy (homepage tile + page blurb) was reworded from the original technical
Mistral/OpenAI-naming framing to something more inviting and non-technical, per user
feedback — see current `frontend/index.html` and
`frontend/features/tool-calling/index.html` for the live wording rather than
duplicating it here (it's been hand-tuned a couple of times already).

## Backend

- **`backend/app/llm_client.py`**: `run_chat` carries an optional `tools` param and a
  `tool_calls: tuple[ToolCall, ...]` field on `ChatResult` (`ToolCall` = `id`, `name`,
  raw `arguments` JSON string, unparsed — parsing/validation is `service.py`'s job).
  `content` is normalized to `""` when the SDK returns `None` (which happens on
  tool-call turns). Unchanged since v1.

- **`backend/app/features/tool_calling/templates.py`** (new in v2): single source of
  truth for shipped templates, same pattern as `llm_quirks/cases.py` /
  `token_efficiency/catalog.py`. `FunctionTemplate` (id, name, description,
  parameter_name, parameter_description, `conditions: list[TemplateCondition]`,
  default_fallback) and `TemplateCondition` (key — fixed, default_value — just a UI
  starting point). `FUNCTION_TEMPLATES` holds the one shipped template;
  `get_template_by_id()` looks one up. **Adding a new template means appending one
  `FunctionTemplate` here — nothing else needs to change** (the `GET /templates`
  endpoint, the frontend picker, and `service.py`'s resolver logic are all driven off
  this registry).

- **`backend/app/features/tool_calling/schemas.py`** (rewritten for v2): a
  discriminated union on a `kind` field replaces the single v1 `FunctionDefinition`:
  - `CustomFunctionDefinition` — `kind: Literal["custom"]`, `name` (pattern
    `^[A-Za-z0-9_-]{1,64}$`), `description`, `mock_result`. No parameters field.
  - `TemplateFunctionInstance` — `kind: Literal["template"]`, `template_id`,
    `values: dict[str, str]` (condition key → user-edited value),
    `fallback_value: str`.
  - `FunctionInput = Annotated[CustomFunctionDefinition | TemplateFunctionInstance,
    Field(discriminator="kind")]`.
  - `ToolCallingRequest` — `query` (non-empty), `functions: list[FunctionInput]` (zero
    allowed, still a deliberate "no tools available" demo). A `model_validator(mode=
    "after")` rejects duplicate function names across the whole list — resolving each
    template instance to its template's fixed `name` first, so a custom function
    colliding with a template's name (or two customs sharing a name) is caught with a
    clear 422 rather than confusing the model with two same-named tools.
  - `ToolCallRecord` / `ToolCallingResponse` — unchanged from v1 (call_id,
    function_name, parsed `arguments`, `raw_arguments`, `matched_function`, `result`;
    response is `tool_calls` + `final_answer`).
  - `FunctionTemplateOut` / `TemplateConditionOut` (new) — what `GET /templates`
    returns for the frontend to render the picker and pre-fill values.
  - `ParameterDefinition` and the v1 generic-parameter concept are gone entirely.

- **`backend/app/features/tool_calling/service.py`** (reworked for v2):
  - `list_function_templates()` — maps `FUNCTION_TEMPLATES` to `FunctionTemplateOut`
    for the router.
  - `_build_tool_schema(fn)` — branches on `isinstance(fn, CustomFunctionDefinition)`:
    custom → `{"type":"object","properties":{}}` (zero-arg); template → looks up the
    `FunctionTemplate` and builds a one-parameter schema with `enum` set to the
    template's condition keys.
  - `_custom_resolver(fn)` / `_template_resolver(fn)` — each returns a small closure
    `(parsed_args) -> str`. Custom's closure always returns `fn.mock_result`. Template's
    closure normalizes the model's argument and the condition keys the same way
    (`.strip().casefold()`), returns the matching edited value or `fn.fallback_value`.
  - `_build_name_and_resolver(fn)` — pairs a function's real name (its own `name` for
    custom, the template's fixed `name` for template) with its resolver, so
    `run_tool_calling` can build one `name -> resolver` dict regardless of kind.
  - `run_tool_calling(query, functions)` flow is otherwise the same shape as v1: first
    call with `tools` (or `None` if `functions` is empty) → if no `tool_calls`, return
    `first.content` directly (mirrors the aspiration script's `else` branch) → else
    build the assistant `tool_calls` message, resolve each call via the
    `name -> resolver` map (unmatched name still produces a non-crashing
    `"Unknown function: X"` tool result + `matched_function=False`, same as v1) → second
    call **without** `tools` (still the deliberate single-round scope boundary) with
    `max_tokens=800` (bumped from the `run_chat` default of 500 after a v1 test came
    close to truncating) → return `tool_calls` + `final_answer`.
  - The v1 `_cast_enum_value` / `_build_json_schema_parameters` generic-parameter
    helpers are deleted.

- **`backend/app/features/tool_calling/router.py`**: `GET /api/tool-calling/templates
  -> list[FunctionTemplateOut]` (new in v2, mirrors `token_efficiency`'s `GET
  /catalog` — frontend needs this server-owned data for the picker and the on-load
  seed). `POST /api/tool-calling/run` unchanged aside from the request schema.

- **`backend/app/main.py`**: router registration unchanged from v1.

## Frontend

- **`frontend/index.html`**: "Tool Calling" card, copy reworded (see Context).
- **`frontend/features/tool-calling/index.html` + `.js`** (`.js` substantially
  reworked for v2): still follows `moderation/` conventions — `.panel` blocks,
  `hidden`-attribute toggling, `apiGet`/`apiPost` from `assets/js/api.js`. DOM stays
  the source of truth (no separate JS model object), same as v1 and as
  `moderation.js`/`token-efficiency.js`.
  - **Functions panel**: `#functions-list` + two add controls — "Add custom function"
    button and an "Add template" `<select>` populated from `GET /templates`, filtered
    to templates not already present (`refreshTemplateSelect()` recomputes this on
    every add/remove by reading `.function-card[data-kind="template"]` elements'
    `data-template-id`).
  - **Custom function card**: `data-kind="custom"` — name input, description
    textarea, one "Answer" textarea. No parameter builder (that's the whole point of
    v2's split).
  - **Template function card**: `data-kind="template"` `data-template-id="..."` — fixed
    `name` shown as plain text (not an input, to signal it's not editable), a
    `TEMPLATE` badge, description + parameter name shown as read-only hint text, one
    `.template-condition-row` per condition (fixed key label + editable value input,
    `data-key` set to the key), and a `.template-fallback-row` (editable, prefilled
    from `default_fallback`).
  - Event delegation on `#functions-list` handles all card removal (works for both
    kinds); the template dropdown's own `change` listener handles adding.
  - `collectFunctions()` branches per `card.dataset.kind`, building either
    `{kind:"custom", name, description, mock_result}` or `{kind:"template",
    template_id, values, fallback_value}`.
  - `validateFunctions()`: custom cards still get the v1 name-pattern +
    non-empty-answer checks; **new in v2** — a duplicate-name check across all cards
    (resolving template cards to their template's real `name` via the in-memory
    `templateCatalog`), so the same "two functions can't share a name" rule that the
    server enforces (schemas.py's validator) also short-circuits client-side with a
    friendly message instead of reaching the server and rendering a raw Pydantic error
    array.
  - **Seed**: on load, `init()` fetches the template catalog, calls
    `refreshTemplateSelect()`, then adds the `get_current_weather` template via the
    same `addTemplateFunctionCard()` path a user clicking the dropdown would use (not a
    hand-built fake card like v1's seed was) and sets the query to `"What's the weather
    like in Boston?"`.
  - `renderToolCall`/`renderResults` unchanged from v1: results still build DOM nodes
    with `.textContent` rather than `innerHTML` for anything that could carry
    model-controlled or user-typed text (function name, arguments, result) — template
    card markup is the one place `innerHTML` is used with interpolation, but only for
    developer-authored `templates.py` constants (name, description, keys, defaults),
    never anything a user or the model supplies.
- **`frontend/assets/css/style.css`**: v1's `.param-row`/`.param-required` (the generic
  parameter-builder styling) were removed since nothing renders them anymore. Added:
  dark-theme `input[type="text"]`/`input[type="number"]` + `input[type="checkbox"]`
  styling (still needed — carried over from v1), `.function-card-kind-label` (the
  `TEMPLATE` badge), `.fn-fixed-name` (monospace, non-editable name display),
  `.add-function-controls` (flex row for the two add controls),
  `.template-condition-row`/`.template-condition-key`/`.template-fallback-row`.
- **`README.md`** / **`CLAUDE.md`**: both updated to describe the two-kind split
  instead of the v1 single-mock-result design. `CLAUDE.md` also gained a one-line "how
  to extend" note pointing at `templates.py` — v1's plan had explicitly said no such
  note was warranted (true at the time, since nothing was a server-owned registry
  yet); `templates.py` now is exactly that pattern, so the note was added rather than
  left stale.

## What's possible next (documented, not built)

Raised when the user asked whether the condition table could be made fully dynamic
(user-defined keys, not just values), in increasing order of complexity:
1. **Generalize the parameter builder** (most likely next step): let a parameter be
   marked "conditional" and let the user add their own key→value rows (+ fallback)
   instead of only picking from a fixed template — reuses the same row-based UI
   pattern v1 had, just scoped to a "conditional" parameter type instead of arbitrary
   parameters.
2. **Templates + a separate fully-custom-conditional flow**: keep templates as-is and
   add option 1 as a third function-creation path alongside custom/template.
3. **Wildcard/fuzzy key matching** (e.g. `"par*"`) layered on top of either — backend
   only, no new UI.
4. **LLM-simulated fallback for unmapped keys** — would reopen the
   static-mock-vs-LLM-simulated trade-off already deliberately decided against
   (decision 1, both v1 and v2) — avoid unless that trade-off is revisited on purpose.

## Verification

1. `uvicorn app.main:app --reload --app-dir backend` (from repo root).
2. `GET /api/tool-calling/templates` returns the one `get_current_weather` template
   with its three conditions and fallback.
3. Homepage: tile copy renders. Tool Calling page: blurb renders, and the
   `get_current_weather` template is pre-seeded via the real add-template path (not a
   hand-built card).
4. "Add template" dropdown shows "All templates added" (disabled) once the one
   template is on the page; remove its card, confirm it reappears and is selectable
   again.
5. "Add custom function" produces a card with no parameter builder — just
   name/description/answer.
6. Edit a condition value directly in the browser (not just via curl), run a query that
   should hit that key, and confirm the *edited* value comes back — proven live: typed
   a distinctive value into the Paris row, asked "What's the weather in Paris right
   now?", got that exact value back in the tool call.
7. Ask about a location not in the list — confirmed via direct resolver test
   (`_template_resolver`) that normalization + fallback works
   (case/whitespace-insensitive match, `None` args, unlisted key all fall back
   correctly); the live model, given the enum-constrained schema, tends to decline to
   call the tool at all for an out-of-enum city rather than call it with a bad value —
   also acceptable behavior, just means the fallback path is easier to prove via direct
   unit-style testing than by prompting.
8. Add a custom function named `get_current_weather` (colliding with the template) and
   confirm both the client-side check (friendly message, no request sent) and the
   server-side 422 (`Duplicate function name: get_current_weather`) reject it.
9. Re-check the other three pages (moderation, llm-quirks, token-efficiency + catalog)
   load without CSS regressions after removing `.param-row`/`.param-required`.
