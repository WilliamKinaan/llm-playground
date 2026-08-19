// Model Evaluation: two independent panels.
//   - "Classify": one-off router call for a single message.
//   - "Test suite": kicks off a background run of every known-answer test
//     case, then polls /run-status until it finishes. The per-test-case
//     results and run-over-run accuracy history live in Phoenix, not here -
//     this page only shows the current run's progress and a link out.

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
const phoenixLinkEl = document.getElementById("phoenix-link");

const POLL_INTERVAL_MS = 1500;
let pollTimer = null;

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
    phoenixLinkEl.href = status.experiment_url || status.dataset_url || "#";
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
runBtn.addEventListener("click", handleRun);
