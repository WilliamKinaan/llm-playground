// Tool Calling demo: lets the user define functions (name, description,
// parameters, a fixed mock result) entirely in the browser, then sends them
// to the model as `tools` alongside a question. The DOM is the source of
// truth for function/parameter state - there's no separate JS model object,
// matching how moderation.js/token-efficiency.js work in this repo.

const NAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

const functionsListEl = document.getElementById("functions-list");
const addFunctionBtn = document.getElementById("add-function-btn");
const queryInput = document.getElementById("query-input");
const runBtn = document.getElementById("run-btn");
const errorEl = document.getElementById("error");
const resultsEl = document.getElementById("results");
const toolCallsSection = document.getElementById("tool-calls-section");
const toolCallsListEl = document.getElementById("tool-calls-list");
const noToolCallsHintEl = document.getElementById("no-tool-calls-hint");
const finalAnswerEl = document.getElementById("final-answer");

function paramRowTemplate() {
  const row = document.createElement("div");
  row.className = "param-row";
  row.innerHTML = `
    <input type="text" class="param-name" placeholder="name" />
    <select class="param-type">
      <option value="string">string</option>
      <option value="number">number</option>
      <option value="integer">integer</option>
      <option value="boolean">boolean</option>
    </select>
    <input type="text" class="param-description" placeholder="description" />
    <label class="param-required"><input type="checkbox" /> required</label>
    <input type="text" class="param-enum" placeholder="allowed values, comma separated (optional)" />
    <button class="button-secondary remove-param-btn" type="button">&times;</button>
  `;
  return row;
}

function functionCardTemplate() {
  const card = document.createElement("div");
  card.className = "panel function-card";
  card.innerHTML = `
    <div class="function-card-header">
      <input type="text" class="fn-name" placeholder="function_name (e.g. get_current_weather)" />
      <button class="button-secondary remove-fn-btn" type="button">Remove</button>
    </div>
    <textarea class="fn-description" placeholder="What this function does (the model reads this to decide when to call it)"></textarea>
    <div class="params-list"></div>
    <button class="button-secondary add-param-btn" type="button">Add parameter</button>
    <label>Mock result <span class="hint">(returned verbatim when this function is called, whatever the arguments)</span></label>
    <textarea class="fn-mock-result" placeholder="e.g. 72°F and sunny"></textarea>
  `;
  return card;
}

function addFunctionCard() {
  const card = functionCardTemplate();
  functionsListEl.appendChild(card);
  return card;
}

function addParamRow(card) {
  const row = paramRowTemplate();
  card.querySelector(".params-list").appendChild(row);
  return row;
}

// Event delegation for all add/remove clicks, since function cards and
// parameter rows are both created and destroyed dynamically.
functionsListEl.addEventListener("click", (event) => {
  if (event.target.matches(".remove-fn-btn")) {
    event.target.closest(".function-card").remove();
  } else if (event.target.matches(".add-param-btn")) {
    addParamRow(event.target.closest(".function-card"));
  } else if (event.target.matches(".remove-param-btn")) {
    event.target.closest(".param-row").remove();
  }
});

addFunctionBtn.addEventListener("click", () => addFunctionCard());

function collectFunctions() {
  return [...functionsListEl.querySelectorAll(".function-card")].map((card) => ({
    name: card.querySelector(".fn-name").value.trim(),
    description: card.querySelector(".fn-description").value.trim(),
    mock_result: card.querySelector(".fn-mock-result").value.trim(),
    parameters: [...card.querySelectorAll(".param-row")].map((row) => ({
      name: row.querySelector(".param-name").value.trim(),
      type: row.querySelector(".param-type").value,
      description: row.querySelector(".param-description").value.trim(),
      required: row.querySelector(".param-required input").checked,
      enum: row
        .querySelector(".param-enum")
        .value.split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    })),
  }));
}

function validateFunctions(functions) {
  for (const fn of functions) {
    if (!fn.name || !NAME_PATTERN.test(fn.name)) {
      return `Function name "${fn.name}" must be 1-64 letters, digits, underscores, or dashes.`;
    }
    if (!fn.mock_result) {
      return `Function "${fn.name}" needs a mock result.`;
    }
    for (const p of fn.parameters) {
      if (!p.name || !NAME_PATTERN.test(p.name)) {
        return `A parameter on function "${fn.name}" needs a valid name.`;
      }
    }
  }
  return null;
}

function renderToolCall(record) {
  // function_name comes straight from the model's output and result is the
  // user's own mock text - both untrusted as far as HTML goes, so build
  // nodes with textContent rather than interpolating into innerHTML.
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

// Seed the page with one editable/removable example on load, so there's
// something to run immediately. Client-side only - there's no server-owned
// catalog here the way token-efficiency has one; the whole point of this
// feature is the user's own functions.
function seedExample() {
  const card = addFunctionCard();
  card.querySelector(".fn-name").value = "get_current_weather";
  card.querySelector(".fn-description").value = "Get the current weather in a given location";
  card.querySelector(".fn-mock-result").value = "72°F and sunny";

  const locationRow = addParamRow(card);
  locationRow.querySelector(".param-name").value = "location";
  locationRow.querySelector(".param-type").value = "string";
  locationRow.querySelector(".param-description").value = "The city and state, e.g. San Francisco, CA";
  locationRow.querySelector(".param-required input").checked = true;

  const unitRow = addParamRow(card);
  unitRow.querySelector(".param-name").value = "unit";
  unitRow.querySelector(".param-type").value = "string";
  unitRow.querySelector(".param-description").value = "Temperature unit";
  unitRow.querySelector(".param-enum").value = "celsius, fahrenheit";

  queryInput.value = "What's the weather like in Boston?";
}

seedExample();
