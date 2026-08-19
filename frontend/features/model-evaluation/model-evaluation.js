// Model Evaluation: three independent pieces.
//   - Departments list + a standing Phoenix link, both populated once on
//     load so the user knows the possible outputs and can see live
//     accuracy without doing anything.
//   - "Classify": one-off router call for a single message, with an example
//     picker (dropdown + "Choose" button) to save typing.
//   - "Test suite": kicks off a background run of every known-answer test
//     case, then polls /run-status until it finishes. The per-test-case
//     results and run-over-run accuracy history live in Phoenix, not here.

const departmentsListEl = document.getElementById("departments-list");
const phoenixSpansLinkEl = document.getElementById("phoenix-spans-link");

const exampleSelectEl = document.getElementById("example-select");
const chooseExampleBtn = document.getElementById("choose-example-btn");

const messageInput = document.getElementById("message-input");
const classifyBtn = document.getElementById("classify-btn");
const classifyErrorEl = document.getElementById("classify-error");
const classifyResultEl = document.getElementById("classify-result");
const departmentBadgeEl = document.getElementById("department-badge");
const reasoningTextEl = document.getElementById("reasoning-text");

const runBtn = document.getElementById("run-btn");
const runErrorEl = document.getElementById("run-error");
const runProgressEl = document.getElementById("run-progress");
const runBarFillEl = document.getElementById("run-bar-fill");
const runProgressTextEl = document.getElementById("run-progress-text");
const runSummaryEl = document.getElementById("run-summary");
const runAccuracyEl = document.getElementById("run-accuracy");

const POLL_INTERVAL_MS = 1500;
let pollTimer = null;
let exampleMessages = []; // fetched once from GET /api/model-evaluation/examples

function renderDepartments(departments) {
  departmentsListEl.innerHTML = "";
  for (const dept of departments) {
    const row = document.createElement("div");
    row.className = "template-condition-row";

    const code = document.createElement("span");
    code.className = "template-condition-key";
    code.textContent = dept.code;

    const description = document.createElement("span");
    description.textContent = dept.description;

    row.append(code, description);
    departmentsListEl.appendChild(row);
  }
}

function renderExampleOptions(examples) {
  for (const [index, example] of examples.entries()) {
    const option = document.createElement("option");
    option.value = String(index);
    const preview = example.message.length > 80 ? `${example.message.slice(0, 80)}...` : example.message;
    option.textContent = `[${example.complexity}] ${preview}`;
    exampleSelectEl.appendChild(option);
  }
}

function handleChooseExample() {
  const index = exampleSelectEl.value;
  if (index === "") return;
  messageInput.value = exampleMessages[Number(index)].message;
}

async function handleClassify() {
  const message = messageInput.value.trim();
  classifyErrorEl.hidden = true;
  classifyResultEl.hidden = true;

  if (!message) {
    classifyErrorEl.textContent = "Enter a customer message first.";
    classifyErrorEl.hidden = false;
    return;
  }

  classifyBtn.disabled = true;
  classifyBtn.textContent = "Classifying...";

  try {
    const result = await apiPost("/api/model-evaluation/classify", { message });
    // department/reasoning come straight from the model - untrusted as far
    // as HTML goes, so use textContent rather than interpolating.
    departmentBadgeEl.textContent = result.department;
    departmentBadgeEl.className = `badge ${result.department === "ESCALATION" ? "flagged" : "clear"}`;
    reasoningTextEl.textContent = result.reasoning;
    classifyResultEl.hidden = false;
  } catch (err) {
    classifyErrorEl.textContent = err.message;
    classifyErrorEl.hidden = false;
  } finally {
    classifyBtn.disabled = false;
    classifyBtn.textContent = "Classify";
  }
}

function renderRunStatus(status) {
  const pct = status.total ? Math.round((status.completed / status.total) * 100) : 0;
  runBarFillEl.style.width = `${pct}%`;
  runProgressTextEl.textContent = `${status.completed} / ${status.total} complete`;
  runProgressEl.hidden = false;

  if (status.status === "done") {
    runSummaryEl.hidden = false;
    const accuracyPct = status.accuracy !== null ? Math.round(status.accuracy * 100) : "?";
    runAccuracyEl.textContent = `Accuracy: ${accuracyPct}%`;
  } else if (status.status === "error") {
    runErrorEl.textContent = status.error || "The test run failed.";
    runErrorEl.hidden = false;
  }
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  runBtn.disabled = false;
  runBtn.textContent = "Run";
}

async function pollRunStatus() {
  try {
    const status = await apiGet("/api/model-evaluation/run-status");
    renderRunStatus(status);
    if (status.status === "done" || status.status === "error") {
      stopPolling();
    }
  } catch (err) {
    runErrorEl.textContent = err.message;
    runErrorEl.hidden = false;
    stopPolling();
  }
}

async function handleRun() {
  runErrorEl.hidden = true;
  runSummaryEl.hidden = true;
  runBtn.disabled = true;
  runBtn.textContent = "Running...";

  try {
    const status = await apiPost("/api/model-evaluation/run-tests", {});
    renderRunStatus(status);
    pollTimer = setInterval(pollRunStatus, POLL_INTERVAL_MS);
  } catch (err) {
    runErrorEl.textContent = err.message;
    runErrorEl.hidden = false;
    stopPolling();
  }
}

classifyBtn.addEventListener("click", handleClassify);
chooseExampleBtn.addEventListener("click", handleChooseExample);
runBtn.addEventListener("click", handleRun);

// Populate the departments list, example picker, and the standing Phoenix
// link as soon as the page loads - all three should be visible without the
// user doing anything.
async function init() {
  const [departments, examples, phoenixLink] = await Promise.all([
    apiGet("/api/model-evaluation/departments"),
    apiGet("/api/model-evaluation/examples"),
    apiGet("/api/model-evaluation/phoenix-link"),
  ]);
  renderDepartments(departments);
  exampleMessages = examples;
  renderExampleOptions(examples);
  phoenixSpansLinkEl.href = phoenixLink.url;
}

init();
