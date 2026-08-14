const listEl = document.getElementById("case-list");
const errorEl = document.getElementById("error");

async function loadCases() {
  try {
    const cases = await apiGet("/api/llm-quirks/cases");
    listEl.innerHTML = "";
    for (const c of cases) {
      const link = document.createElement("a");
      link.className = "feature-card";
      link.href = `${c.id}/`;
      link.innerHTML = `<h2>${c.title}</h2><p>${c.teaser}</p>`;
      listEl.appendChild(link);
    }
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
}

loadCases();
