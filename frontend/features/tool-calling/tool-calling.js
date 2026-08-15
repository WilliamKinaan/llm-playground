// Tool Calling demo: two kinds of functions.
//   - "custom": fully user-authored, no parameters, one fixed answer.
//   - "template": pre-built by us (name/description/parameter/condition keys
//     fixed), the user can only edit the value returned per key + a fallback.
// The DOM is the source of truth for both - there's no separate JS model
// object, matching how moderation.js/token-efficiency.js work in this repo.

const NAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

const functionsListEl = document.getElementById("functions-list");
const addCustomBtn = document.getElementById("add-custom-btn");
const addTemplateSelect = document.getElementById("add-template-select");
const queryInput = document.getElementById("query-input");
const runBtn = document.getElementById("run-btn");
const errorEl = document.getElementById("error");
const resultsEl = document.getElementById("results");
const toolCallsSection = document.getElementById("tool-calls-section");
const toolCallsListEl = document.getElementById("tool-calls-list");
const noToolCallsHintEl = document.getElementById("no-tool-calls-hint");
const finalAnswerEl = document.getElementById("final-answer");

let templateCatalog = []; // fetched once from GET /api/tool-calling/templates

function usedTemplateIds() {
  return new Set(
    [...functionsListEl.querySelectorAll('.function-card[data-kind="template"]')].map(
      (card) => card.dataset.templateId
    )
  );
}

function refreshTemplateSelect() {
  const used = usedTemplateIds();
  const available = templateCatalog.filter((t) => !used.has(t.id));

  addTemplateSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.disabled = true;
  placeholder.selected = true;
  placeholder.textContent = available.length ? "Add template..." : "All templates added";
  addTemplateSelect.appendChild(placeholder);

  for (const t of available) {
    const option = document.createElement("option");
    option.value = t.id;
    option.textContent = t.name;
    addTemplateSelect.appendChild(option);
  }
  addTemplateSelect.disabled = available.length === 0;
}

function customFunctionCardTemplate() {
  const card = document.createElement("div");
  card.className = "panel function-card";
  card.dataset.kind = "custom";
  card.innerHTML = `
    <div class="function-card-header">
      <input type="text" class="fn-name" placeholder="function_name (e.g. get_world_cup_winner)" />
      <button class="button-secondary remove-fn-btn" type="button">Remove</button>
    </div>
    <textarea class="fn-description" placeholder="What this function does (the model reads this to decide when to call it)"></textarea>
    <label>Answer <span class="hint">(returned whenever this function is called)</span></label>
    <textarea class="fn-mock-result" placeholder="e.g. Italy"></textarea>
  `;
  return card;
}

function addCustomFunctionCard() {
  const card = customFunctionCardTemplate();
  functionsListEl.appendChild(card);
  return card;
}

function templateFunctionCardTemplate(template) {
  const card = document.createElement("div");
  card.className = "panel function-card";
  card.dataset.kind = "template";
  card.dataset.templateId = template.id;

  const conditionRows = template.conditions
    .map(
      (c) => `
      <div class="template-condition-row" data-key="${c.key}">
        <span class="template-condition-key">${c.key}</span>
        <input type="text" class="template-condition-value" value="${c.default_value}" />
      </div>`
    )
    .join("");

  card.innerHTML = `
    <div class="function-card-header">
      <span class="function-card-kind-label">Template</span>
      <span class="fn-fixed-name">${template.name}</span>
      <button class="button-secondary remove-fn-btn" type="button">Remove</button>
    </div>
    <div class="hint">${template.description} — parameter: <code>${template.parameter_name}</code></div>
    <div class="template-conditions">${conditionRows}</div>
    <div class="template-condition-row template-fallback-row">
      <span class="template-condition-key">Fallback</span>
      <input type="text" class="template-fallback-value" value="${template.default_fallback}" />
    </div>
    <div class="hint">Fallback is used when the model asks about something outside the list above.</div>
  `;
  return card;
}

function addTemplateFunctionCard(template) {
  const card = templateFunctionCardTemplate(template);
  functionsListEl.appendChild(card);
  refreshTemplateSelect();
  return card;
}

// Event delegation for removes, since cards are created and destroyed dynamically.
functionsListEl.addEventListener("click", (event) => {
  if (event.target.matches(".remove-fn-btn")) {
    event.target.closest(".function-card").remove();
    refreshTemplateSelect();
  }
});

addCustomBtn.addEventListener("click", () => addCustomFunctionCard());

addTemplateSelect.addEventListener("change", () => {
  const templateId = addTemplateSelect.value;
  if (!templateId) return;
  const template = templateCatalog.find((t) => t.id === templateId);
  if (template) addTemplateFunctionCard(template);
});

function collectFunctions() {
  return [...functionsListEl.querySelectorAll(".function-card")].map((card) => {
    if (card.dataset.kind === "custom") {
      return {
        kind: "custom",
        name: card.querySelector(".fn-name").value.trim(),
        description: card.querySelector(".fn-description").value.trim(),
        mock_result: card.querySelector(".fn-mock-result").value.trim(),
      };
    }
    const values = {};
    for (const row of card.querySelectorAll(".template-condition-row:not(.template-fallback-row)")) {
      values[row.dataset.key] = row.querySelector(".template-condition-value").value;
    }
    return {
      kind: "template",
      template_id: card.dataset.templateId,
      values,
      fallback_value: card.querySelector(".template-fallback-value").value,
    };
  });
}

function validateFunctions(functions) {
  const seenNames = new Set();
  for (const fn of functions) {
    let name;
    if (fn.kind === "custom") {
      if (!fn.name || !NAME_PATTERN.test(fn.name)) {
        return `Function name "${fn.name}" must be 1-64 letters, digits, underscores, or dashes.`;
      }
      if (!fn.mock_result) {
        return `Function "${fn.name}" needs an answer.`;
      }
      name = fn.name;
    } else {
      const template = templateCatalog.find((t) => t.id === fn.template_id);
      name = template ? template.name : fn.template_id;
    }
    if (seenNames.has(name)) {
      return `Two functions are both named "${name}" — rename your custom function so it doesn't collide.`;
    }
    seenNames.add(name);
  }
  return null;
}

function renderToolCall(record) {
  // function_name comes straight from the model's output and result is
  // user-supplied text - both untrusted as far as HTML goes, so build nodes
  // with textContent rather than interpolating into innerHTML.
  const badgeClass = record.matched_function ? "clear" : "flagged";
  const badgeText = record.matched_function ? "matched" : "unknown function";
  const argsText =
    record.arguments !== null
      ? JSON.stringify(record.arguments)
      : `${record.raw_arguments} (invalid JSON)`;

  const card = document.createElement("div");
  card.className = "variant-card";

  const label = document.createElement("div");
  label.className = "variant-label";
  label.textContent = record.function_name;

  const badge = document.createElement("span");
  badge.className = `badge ${badgeClass}`;
  badge.textContent = badgeText;

  const argsEl = document.createElement("div");
  argsEl.className = "variant-prompt";
  argsEl.textContent = `Arguments: ${argsText}`;

  const outputEl = document.createElement("div");
  outputEl.className = "variant-output";
  outputEl.textContent = record.result;

  card.append(label, badge, argsEl, outputEl);
  return card;
}

function renderResults(result) {
  toolCallsListEl.innerHTML = "";

  if (result.tool_calls.length === 0) {
    toolCallsSection.hidden = true;
    noToolCallsHintEl.hidden = false;
  } else {
    toolCallsSection.hidden = false;
    noToolCallsHintEl.hidden = true;
    for (const record of result.tool_calls) {
      toolCallsListEl.appendChild(renderToolCall(record));
    }
  }

  finalAnswerEl.textContent = result.final_answer;
  resultsEl.hidden = false;
}

async function handleRun() {
  const query = queryInput.value.trim();
  errorEl.hidden = true;

  if (!query) {
    errorEl.textContent = "Enter a question first.";
    errorEl.hidden = false;
    return;
  }

  const functions = collectFunctions();
  const validationError = validateFunctions(functions);
  if (validationError) {
    errorEl.textContent = validationError;
    errorEl.hidden = false;
    return;
  }

  runBtn.disabled = true;
  runBtn.textContent = "Running...";
  resultsEl.hidden = true;

  try {
    const result = await apiPost("/api/tool-calling/run", { query, functions });
    renderResults(result);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run";
  }
}

runBtn.addEventListener("click", handleRun);

// Load the template catalog, populate the picker, and seed the page with
// the get_current_weather template so there's something to run immediately.
async function init() {
  templateCatalog = await apiGet("/api/tool-calling/templates");
  refreshTemplateSelect();

  const weatherTemplate = templateCatalog.find((t) => t.id === "get_current_weather");
  if (weatherTemplate) {
    addTemplateFunctionCard(weatherTemplate);
    queryInput.value = "What's the weather like in Boston?";
  }
}

init();
