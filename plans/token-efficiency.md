# Token Efficiency — Feature Plan

## Context
Third top-level feature for `llm-playground` (sibling to Content Moderation and LLM
Quirks), demonstrating a real prompt-engineering technique from
`~/Documents/ai/openai/sequence.py`: classify-then-answer (2 small calls) vs. stuffing
an entire product catalog into one big prompt (1 call).

**Assumption validated before planning, using real API usage numbers (not estimates)** —
ran both approaches against the live Mistral API with `sequence.py`'s exact 24-product
catalog and system prompts:

| Query | Chained (2 calls) | Single prompt (1 call) | Savings |
|---|---|---|---|
| "smartx pro phone, fotosnap DSLR, and your TVs" | 1,763 tokens | 4,246 tokens | 58.5% fewer |
| "Do you have a wireless charger?" | 685 tokens | 3,907 tokens | 82.5% fewer |

Mechanism confirmed: the one-shot approach pays for the *entire* catalog every request;
the chain's classification step is cheap (~400-450 tokens) and the second step only
injects the 1-3 actually-relevant products. Narrower questions save proportionally more.
Both approaches give comparably good, grounded answers — **not identical text** (worth
being precise about this in the UI copy, since outputs will differ in wording even at
temperature 0).

Agreed with user:
- Feature name: **Token Efficiency** (slug: `token-efficiency`)
- Input: **both** a dropdown of curated sample queries (built from the real product
  catalog) *and* a freely-editable textarea — selecting a dropdown option fills the
  textarea, which the user can still edit before clicking Compare
- A **"see what we sell"** link/page so free-text users know what's actually in the
  catalog to ask about (opens in a new tab so their typed query isn't lost)
- One click runs both pipelines against the same query and shows real per-step token
  usage side by side

## Backend

- **`backend/app/llm_client.py`**: add `run_chat(messages, temperature=0, json_mode=False,
  max_tokens=500)` — a generic multi-message helper (system+user turns, optional JSON
  mode) that also returns the API's real usage numbers (`prompt_tokens`,
  `completion_tokens`, `total_tokens`). The existing `run_chat_completion` (single
  user-string, no usage) and `run_moderation` are untouched — this is additive, for
  features that need full message control and token accounting.
- **New feature module `backend/app/features/token_efficiency/`**:
  - `catalog.py` — the product catalog (ported from `sequence.py`, 24 products/6
    categories) plus the classification and answering system-prompt templates, as data.
    Single source of truth for both the comparison endpoint and the "what we sell" page.
  - `schemas.py` — `SampleQuery` (label, query); `StepUsage` (prompt/completion/total);
    `ChainedResult` (classification output, its usage, final answer, its usage, combined
    total); `SingleShotResult` (answer, usage); `CompareResponse` (both results +
    computed `tokens_saved` / `tokens_saved_pct`); `CatalogCategory` (name, products).
  - `service.py` — `list_sample_queries()`, `get_catalog()`, and `compare(query)`, which
    runs the **chained pipeline** (classify → look up matched products → answer) and the
    **single-shot pipeline** (whole catalog embedded in the system prompt → answer)
    **concurrently on two threads** (same pattern as the LLM Quirks fox-chicken-grain
    case) so total wait is roughly the slower one, not the sum of three calls.
  - `router.py` — `GET /api/token-efficiency/sample-queries`,
    `GET /api/token-efficiency/catalog`, `POST /api/token-efficiency/compare`.
- **`backend/app/main.py`**: register the new router.

## Frontend

- **`frontend/index.html`**: add a "Token Efficiency" card.
- **`frontend/features/token-efficiency/index.html` + `.js`**:
  - dropdown (from `GET /sample-queries`) that fills the textarea on selection; textarea
    stays freely editable regardless of source
  - "See what we sell →" link, `target="_blank"`, to the catalog page
  - one "Compare" button, calls `POST /compare`
  - two result panels side by side: **"Chained (2 calls)"** (shows the classification
    step compactly, then the final answer, with a token-usage line per step and a bolded
    total) and **"Single Prompt (1 call)"** (final answer directly, with its token-usage
    line)
  - a summary strip: total tokens for each side + "~N% fewer tokens with chaining",
    with a simple two-bar visual comparison reusing the existing `.bar-track`/`.bar-fill`
    component already built for moderation's category scores (no new charting code)
  - copy is explicit that answers are *comparable*, not byte-identical
- **`frontend/features/token-efficiency/catalog.html` + `.js`**: fetches
  `GET /catalog`, renders products grouped by category — simple read-only browse page,
  reusing existing panel/grid CSS.
- **`frontend/assets/css/style.css`**: extend with the two-column compare layout and
  step-block styling; reuse existing tokens/panel/badge/bar patterns rather than
  introducing new visual language.

## Verification
1. `GET /api/token-efficiency/sample-queries` and `/catalog` return sane data.
2. `POST /compare` with the two already-validated queries above reproduces real token
   counts with chained < single-shot in both cases.
3. Browser: dropdown fills the textarea; catalog link opens in a new tab without losing
   the typed query; Compare renders both panels with real numbers and the savings
   summary; try one custom free-text query too.
4. Curate 2-3 dropdown sample queries during implementation, each verified live before
   being added (same standard used for LLM Quirks cases) — e.g. a category-level query
   ("What laptops do you have?") in addition to the two already tested, to show the
   effect at a third scale.
