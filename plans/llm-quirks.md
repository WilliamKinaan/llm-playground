# LLM Quirks — Feature Plan

## Context
Second feature for the `llm-playground` prototype (repo root:
`/Users/williamkinaan/Documents/ai/llm-playground`). Where "Content Moderation" shows a
single API call, this feature showcases specific, surprising, *reproducible* LLM
behaviors — starting with letter-reversal breaking on certain models because of how the
tokenizer segments the word (e.g. an older tokenizer splitting "lollipop" into 3 tokens
vs. a newer one into 2, which changes whether letter-by-letter reversal assembles back
into the right word). More cases will be added later; the feature must be structured so
adding one is cheap (new data entry + one small page), not a rewrite.

Agreed with user:
- Feature name: **LLM Quirks** (slug: `llm-quirks`)
- Each prompt is fixed/curated — no free-text input, just a "Go" button
- Calls are **live** against Mistral each time (not cached/canned transcripts)
- The lollipop case shows two prompt variants side by side ("reverse lollipop" vs
  "reverse l-o-l-l-i-p-o-p") so the divergence is visible in one glance
- The curated explanation of *why* is hidden until the user clicks Go and sees the real
  output, then reveals it (own "Why?" toggle) — teaches the mechanism, not just shows a
  weird result
- Each case gets its own page/URL (like moderation), reached from an index page for the
  feature — not one long scrolling page

## Data model (single source of truth: backend)
A case registry in the backend, so the frontend never hardcodes prompts/explanations:
```
CaseDefinition:
  id: str              # slug, e.g. "lollipop-reversal"
  title: str
  teaser: str           # one-liner for the index card
  description: str       # short setup text shown on the case page before Go
  variants: [{ label: str, prompt: str, expected: str | None }]  # expected optional,
                                                                    # used for auto ✓/✗
                                                                    # only when unambiguous
  explanation: str        # revealed after Go via "Why?"
```
Seed content (only case for now):
- id `lollipop-reversal`, variants: `"Take the letters in lollipop and reverse them"` and
  `"Take the letters in l-o-l-l-i-p-o-p and reverse them"` (the literal `"reverse lollipop"`
  phrasing originally tried turned out ambiguous in testing — Mistral read it as "what is
  a reverse lollipop" and answered off-topic, so the prompts were tightened to remove
  that ambiguity while keeping the same comparison), no `expected` (correctness here is best judged visually — the dash variant could
  legitimately reverse to a dashed string, so a strict string-match grade would be
  misleading). Explanation covers tokenization: the model reverses letter-by-letter
  correctly as an intermediate step, but reassembles the final token sequence using its
  tokenizer's actual token boundaries for the word, which don't line up with individual
  letters — so the final answer can still come out wrong even though the reasoning was
  right; a tokenizer update that changes "lollipop" from 3 tokens to 2 changes this
  behavior on the same model family.

## Backend
- `backend/app/llm_client.py`: add `run_chat_completion(prompt, temperature=0)` helper
  (mirrors the existing `run_moderation`, reuses `get_client()`/`get_settings()`, uses
  `settings.mistral_chat_model`).
- New feature module `backend/app/features/llm_quirks/`:
  - `cases.py` — the registry (Python list of `CaseDefinition`s); this is the file every
    future quirk gets added to.
  - `schemas.py` — `CaseSummary` (id, title, teaser), `CaseDetail` (+ description,
    variants without outputs, explanation), `VariantResult` (label, prompt, output,
    matches_expected), `RunResponse` (list of `VariantResult`).
  - `service.py` — `list_cases()`, `get_case(id)`, `run_case(id)` (calls
    `run_chat_completion` once per variant; on a per-variant API error, still return the
    other variants' results with an error message on the failed one rather than failing
    the whole request).
  - `router.py`:
    - `GET /api/llm-quirks/cases` → `[CaseSummary]`
    - `GET /api/llm-quirks/cases/{case_id}` → `CaseDetail`
    - `POST /api/llm-quirks/cases/{case_id}/run` → `RunResponse` (runs every variant)
- `backend/app/main.py`: include the new router next to the moderation one.

## Frontend
- `frontend/index.html`: add an "LLM Quirks" card linking to `/features/llm-quirks/`.
- `frontend/features/llm-quirks/index.html` + `quirks-index.js`: fetch
  `GET /api/llm-quirks/cases`, render a card per case linking to that case's own page.
- `frontend/features/llm-quirks/case.js` — **shared** script included by every case
  page: reads a `data-case-id` attribute off a container element, fetches
  `GET .../cases/{id}`, renders the description + one card per variant (prompt shown,
  output slot empty), wires a single "Go" button that calls
  `POST .../cases/{id}/run` and fills in each variant's output, then reveals a "Why?"
  button that shows the `explanation` text.
- Per case, a thin page, e.g. `frontend/features/llm-quirks/lollipop-reversal/index.html`
  — just the shared `<link>`/`<script>` includes plus a container div with
  `data-case-id="lollipop-reversal"`. Adding a future case = one new small HTML file
  like this + one new entry in `cases.py`; `case.js` and the API are not touched.
- `frontend/assets/js/api.js`: add an `apiGet()` helper alongside the existing
  `apiPost()`, reused by both the index and case pages (no per-page fetch duplication).
- `frontend/assets/css/style.css`: extend with styles for the side-by-side variant
  cards and the "Why?" reveal panel, reusing existing tokens/badge/panel patterns rather
  than introducing a new visual language.

## Verification
1. Start the backend (`uvicorn app.main:app --reload --app-dir backend` from repo root).
2. `GET /api/llm-quirks/cases` returns the lollipop case; `GET .../cases/lollipop-reversal`
   returns its two variants + explanation text.
3. Load `/features/llm-quirks/` → see the lollipop card → open it.
4. Click "Go" → both variants show real, live Mistral output side by side (no page
   reload, no cached values — re-clicking Go re-calls the API).
5. Click "Why?" → curated explanation appears.
6. Confirm the landing page's new card and the moderation feature are unaffected.
7. Once approved, write this plan to `plans/llm-quirks.md` in the repo (mirroring how
   `plans/initialsetupplan.md` was committed for the first feature).
