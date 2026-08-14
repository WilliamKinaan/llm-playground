// Shared by every LLM Quirks case page. The page only needs a container
// element with a `data-case-id` attribute; everything else (title,
// description, prompts, explanation) comes from the backend so a new case
// never needs new JS.

const root = document.getElementById("quirk-root");
const caseId = root.dataset.caseId;

const titleEl = document.getElementById("case-title");
const descriptionEl = document.getElementById("case-description");
const variantListEl = document.getElementById("variant-list");
const goBtn = document.getElementById("go-btn");
const whyBtn = document.getElementById("why-btn");
const explanationEl = document.getElementById("explanation");
const errorEl = document.getElementById("error");

let explanation = "";
let streaming = false;

function renderVariants(variants) {
  variantListEl.innerHTML = "";
  for (const variant of variants) {
    const card = document.createElement("div");
    card.className = "variant-card";
    card.dataset.label = variant.label;
    card.innerHTML = `
      <div class="variant-label">${variant.label}</div>
      <div class="variant-prompt">&ldquo;${variant.prompt}&rdquo;</div>
      <div class="variant-output placeholder">Click Go to run this prompt live.</div>
    `;
    variantListEl.appendChild(card);
  }
}

async function loadCase() {
  try {
    const detail = await apiGet(`/api/llm-quirks/cases/${caseId}`);
    document.title = `${detail.title} — LLM Playground`;
    titleEl.textContent = detail.title;
    descriptionEl.textContent = detail.description;
    explanation = detail.explanation;
    streaming = detail.streaming;
    renderVariants(detail.variants);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
}

function resetOutputsToThinking() {
  for (const output of variantListEl.querySelectorAll(".variant-output")) {
    output.innerHTML = '<span class="thinking"><span class="spinner"></span>Thinking&hellip;</span>';
    output.classList.add("placeholder");
  }
}

async function runBuffered() {
  const { results } = await apiPost(`/api/llm-quirks/cases/${caseId}/run`);
  const cards = [...variantListEl.querySelectorAll(".variant-card")];
  results.forEach((result, i) => {
    const output = cards[i].querySelector(".variant-output");
    output.textContent = result.output;
    output.classList.remove("placeholder");

    if (result.matches_expected !== null) {
      const badge = document.createElement("span");
      badge.className = `badge result-badge ${result.matches_expected ? "clear" : "flagged"}`;
      badge.textContent = result.matches_expected ? "✓ Correct" : "✗ Incorrect";
      output.appendChild(badge);
    }
  });
}

async function runStreaming() {
  const cards = [...variantListEl.querySelectorAll(".variant-card")];
  const outputs = cards.map((card) => card.querySelector(".variant-output"));
  const started = outputs.map(() => false);

  for await (const message of apiPostStream(`/api/llm-quirks/cases/${caseId}/run-stream`)) {
    if (message.type === "complete") break;

    const output = outputs[message.variant];
    if (!output) continue; // e.g. a top-level {"type": "error", ...} with no variant

    if (message.type === "delta") {
      if (!started[message.variant]) {
        output.textContent = "";
        output.classList.remove("placeholder");
        started[message.variant] = true;
      }
      output.textContent += message.text;
    } else if (message.type === "error") {
      output.textContent = `(error calling the model: ${message.text})`;
      output.classList.remove("placeholder");
    }
    // "done" for one variant just means that variant's stream ended —
    // the other variant may still be streaming, so keep waiting for "complete".
  }
}

async function handleGo() {
  errorEl.hidden = true;
  goBtn.disabled = true;
  goBtn.textContent = "Thinking...";
  resetOutputsToThinking();

  try {
    await (streaming ? runStreaming() : runBuffered());
    whyBtn.hidden = false;
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = "Go";
  }
}

function handleWhy() {
  // Explanation text is curated app data (not user input) and may contain a
  // link, e.g. to the OpenAI tokenizer tool, so it's rendered as HTML.
  explanationEl.innerHTML = explanation;
  explanationEl.hidden = false;
  whyBtn.hidden = true;
}

goBtn.addEventListener("click", handleGo);
whyBtn.addEventListener("click", handleWhy);

loadCase();
