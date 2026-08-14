const textInput = document.getElementById("text-input");
const submitBtn = document.getElementById("submit-btn");
const resultsEl = document.getElementById("results");
const badgeEl = document.getElementById("badge");
const categoriesEl = document.getElementById("categories");
const errorEl = document.getElementById("error");

function renderResults(result) {
  badgeEl.textContent = result.flagged ? "Flagged" : "Clear";
  badgeEl.className = `badge ${result.flagged ? "flagged" : "clear"}`;

  categoriesEl.innerHTML = "";
  for (const category of result.categories) {
    const row = document.createElement("div");
    row.className = `category-row${category.flagged ? " is-flagged" : ""}`;

    const pct = Math.round(category.score * 100);
    row.innerHTML = `
      <span class="name">${category.name.replace(/_/g, " ")}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></span>
      <span class="score">${pct}%</span>
    `;
    categoriesEl.appendChild(row);
  }

  resultsEl.hidden = false;
}

async function handleSubmit() {
  const text = textInput.value.trim();
  errorEl.hidden = true;
  resultsEl.hidden = true;

  if (!text) {
    errorEl.textContent = "Enter some text first.";
    errorEl.hidden = false;
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Checking...";

  try {
    const result = await apiPost("/api/moderation/check", { text });
    renderResults(result);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Check text";
  }
}

submitBtn.addEventListener("click", handleSubmit);
