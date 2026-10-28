/* Design-system helpers.
 *
 * Identifier typography (docs/ui/DESIGN_SYSTEM.md §8): anything that is
 * literally a machine identifier — record IDs, asset tags, serial numbers,
 * barcodes, session and resource IDs — is shown in the monospace identifier
 * face (.text-mono-id) instead of the sans, so an ID reads as an ID next to
 * prose. The tables are drawn by several scripts (app.js, reports.js,
 * masters.js), so rather than touching every renderer this marks the cells
 * after any table is (re)drawn, by the column's own heading.
 *
 * Loaded before app.js; it only reads the DOM.
 */
(function () {
  "use strict";

  const ID_HEADING = /^(id|asset[ _]?tag|serial([ _]number)?|barcode|resource[ _]?id|value[ _]?id|user[ _]?id|employee[ _]?id|employee[ _]?code|jti|session)$/i;

  function markTable(table) {
    const heads = Array.from(table.querySelectorAll("thead th")).map((th) => th.textContent.replace(/[▲▼↑↓]/g, "").replace(/\s+/g, " ").trim());
    const columns = [];
    heads.forEach((text, index) => {
      if (ID_HEADING.test(text)) columns.push(index);
    });
    if (!columns.length) return;
    table.querySelectorAll("tbody tr").forEach((row) => {
      columns.forEach((index) => {
        const cell = row.cells[index];
        if (cell && !cell.classList.contains("text-mono-id")) cell.classList.add("text-mono-id");
      });
    });
  }

  let scheduled = false;
  function markAll() {
    scheduled = false;
    document.querySelectorAll("#app table").forEach(markTable);
  }

  function start() {
    const app = document.getElementById("app");
    if (!app || typeof MutationObserver === "undefined") return;
    new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(markAll);
    }).observe(app, { childList: true, subtree: true });
    markAll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
