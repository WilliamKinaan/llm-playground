const sampleSelect = document.getElementById("sample-select");
const queryInput = document.getElementById("query-input");
const compareBtn = document.getElementById("compare-btn");
const errorEl = document.getElementById("error");
const resultsEl = document.getElementById("results");

const option1Output = document.getElementById("option1-output");
const option1Usage = document.getElementById("option1-usage");
const option2Output = document.getElementById("option2-output");
const option2Usage = document.getElementById("option2-usage");

const option1Bar = document.getElementById("option1-bar");
const option1BarLabel = document.getElementById("option1-bar-label");
const option2Bar = document.getElementById("option2-bar");
const option2BarLabel = document.getElementById("option2-bar-label");
const savingsLine = document.getElementById("savings-line");

const whyBtn = document.getElementById("why-btn");
const explanationEl = document.getElementById("explanation");

async function loadSampleQueries() {
  const samples = await apiGet("/api/token-efficiency/sample-queries");
  sampleSelect.innerHTML = "";
  for (const sample of samples) {
    const option = document.createElement("option");
    option.value = sample.query;
    option.textContent = sample.label;
    sampleSelect.appendChild(option);
  }
  if (samples.length > 0) {
    queryInput.value = samples[0].query;
  }
}

sampleSelect.addEventListener("change", () => {
  queryInput.value = sampleSelect.value;
});

async function handleCompare() {
  const query = queryInput.value.trim();
  errorEl.hidden = true;

  if (!query) {
    errorEl.textContent = "Enter a question first.";
    errorEl.hidden = false;
    return;
  }

  compareBtn.disabled = true;
  compareBtn.textContent = "Comparing...";
  resultsEl.hidden = true;
  whyBtn.hidden = true;
  explanationEl.hidden = true;

  try {
    const result = await apiPost("/api/token-efficiency/compare", { query });

    option1Output.textContent = result.chained.answer;
    option1Output.classList.remove("placeholder");
    option1Usage.textContent = `${result.chained.total_tokens} tokens`;

    option2Output.textContent = result.single_shot.answer;
    option2Output.classList.remove("placeholder");
    option2Usage.textContent = `${result.single_shot.usage.total_tokens} tokens`;

    const maxTokens = Math.max(result.chained.total_tokens, result.single_shot.usage.total_tokens);
    option1Bar.style.width = `${(result.chained.total_tokens / maxTokens) * 100}%`;
    option1BarLabel.textContent = `${result.chained.total_tokens}`;
    option2Bar.style.width = `${(result.single_shot.usage.total_tokens / maxTokens) * 100}%`;
    option2BarLabel.textContent = `${result.single_shot.usage.total_tokens}`;

    savingsLine.innerHTML = `Option 1 used <strong>${result.tokens_saved_pct}% fewer tokens</strong> (${result.tokens_saved} fewer) for this question.`;

    resultsEl.hidden = false;
    whyBtn.hidden = false;
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    compareBtn.disabled = false;
    compareBtn.textContent = "Compare";
  }
}

function handleWhy() {
  explanationEl.hidden = false;
  whyBtn.hidden = true;
}

compareBtn.addEventListener("click", handleCompare);
whyBtn.addEventListener("click", handleWhy);

loadSampleQueries();
