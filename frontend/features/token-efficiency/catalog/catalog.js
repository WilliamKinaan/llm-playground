const catalogEl = document.getElementById("catalog");
const errorEl = document.getElementById("error");

async function loadCatalog() {
  try {
    const categories = await apiGet("/api/token-efficiency/catalog");
    catalogEl.innerHTML = "";

    for (const category of categories) {
      const section = document.createElement("section");
      section.className = "panel catalog-category";

      const heading = document.createElement("h2");
      heading.textContent = category.name;
      section.appendChild(heading);

      const grid = document.createElement("div");
      grid.className = "variant-grid";

      for (const product of category.products) {
        const card = document.createElement("div");
        card.className = "variant-card";
        card.innerHTML = `
          <div class="variant-label">${product.brand}</div>
          <div class="variant-prompt">${product.name} &mdash; $${product.price.toFixed(2)}</div>
          <div class="variant-output">${product.description}</div>
        `;
        grid.appendChild(card);
      }

      section.appendChild(grid);
      catalogEl.appendChild(section);
    }
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
}

loadCatalog();
