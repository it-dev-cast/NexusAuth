/* Reports page.
 *
 * Everything on this page is driven by the backend's report catalog
 * (GET /api/v1/reports/catalog): which reports exist for the signed-in role,
 * their columns, which columns sort, and which filters they accept. Nothing
 * about a report is hardcoded here, so the UI can't offer something the
 * server would refuse, and a new report added in
 * app/services/report_service.py shows up with no change to this file.
 *
 * URL = state. #reports                      -> landing (summary + report list)
 *       #reports/<key>?<filters>&sort_by=..  -> one report. Filters, sort, page
 *       and page size are all in the hash, so refresh, Back/Forward and copied
 *       links land on exactly the same view. Applying filters/sorting/paging
 *       uses replaceState (no history entry per click); opening a report from
 *       the list is a real navigation, so Back returns to the list.
 *
 * Loaded BEFORE app.js (see index.html) and deliberately touches none of
 * app.js's bindings at load time — only inside functions that run once the
 * section is opened — so the load order can't cause a use-before-define.
 */
(function () {
  "use strict";

  const PAGE_SIZES = [10, 25, 50, 100];
  const DEFAULT_SIZE = 25;
  const STALE_MS = 30000; // re-entering an already-rendered view refreshes after this
  const GOOD = new Set(["active", "approved", "certified", "login_success", "internal"]);
  const BAD = new Set(["exited", "disposed", "suspended", "inactive", "login_failure", "access_denied", "refresh_reuse_detected"]);

  const rp = {
    userId: null,
    catalog: null,
    options: null,
    summary: null,
    category: "all",
    query: "",
    view: null, // applied view state of the open report
    spec: null,
    seq: 0, // bumped on every render so a slow response can't overwrite a newer one
    rendered: false,
    renderedAt: 0,
    lastHash: null,
    wired: false,
    lastData: null,
  };

  const esc = (value) => escapeHtml(value == null ? "" : String(value));
  const root = () => document.getElementById("reports-root");

  /* ------------------------------------------------------------------ */
  /* Routing                                                             */
  /* ------------------------------------------------------------------ */
  function parseRoute() {
    const raw = location.hash.replace(/^#/, "");
    const cut = raw.indexOf("?");
    const path = cut === -1 ? raw : raw.slice(0, cut);
    const query = cut === -1 ? "" : raw.slice(cut + 1);
    const segments = path.split("/");
    let key = null;
    if (segments[1]) {
      try {
        key = decodeURIComponent(segments[1]);
      } catch (error) {
        key = segments[1];
      }
    }
    return { key, params: new URLSearchParams(query) };
  }

  function viewFromParams(spec, params) {
    const filters = {};
    for (const filter of spec.filters) {
      const value = params.get(filter.name);
      if (value) filters[filter.name] = value;
    }
    const sortable = spec.columns.filter((c) => c.sortable).map((c) => c.key);
    let sortBy = params.get("sort_by");
    if (!sortable.includes(sortBy)) sortBy = spec.default_sort;
    let sortDir = params.get("sort_dir");
    if (sortDir !== "asc" && sortDir !== "desc") sortDir = sortBy === spec.default_sort ? spec.default_dir : "asc";
    let size = parseInt(params.get("size"), 10);
    if (!PAGE_SIZES.includes(size)) size = DEFAULT_SIZE;
    let page = parseInt(params.get("page"), 10);
    if (!(page >= 1)) page = 1;
    return { key: spec.key, filters, sortBy, sortDir, size, page };
  }

  function hashFor(spec, view) {
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(view.filters)) params.set(name, value);
    const isDefaultSort = view.sortBy === spec.default_sort && view.sortDir === spec.default_dir;
    if (!isDefaultSort) {
      params.set("sort_by", view.sortBy);
      params.set("sort_dir", view.sortDir);
    }
    if (view.size !== DEFAULT_SIZE) params.set("size", String(view.size));
    if (view.page > 1) params.set("page", String(view.page));
    const query = params.toString();
    return `#reports/${encodeURIComponent(spec.key)}${query ? "?" + query : ""}`;
  }

  // Keep the address bar in step with the view without adding a history entry.
  function syncUrl(spec, view) {
    const hash = hashFor(spec, view);
    if (location.hash !== hash) history.replaceState(null, "", hash);
    rp.lastHash = location.hash;
  }

  function queryString(view, { paginate }) {
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(view.filters)) params.set(name, value);
    params.set("sort_by", view.sortBy);
    params.set("sort_dir", view.sortDir);
    if (paginate) {
      params.set("limit", String(view.size));
      params.set("offset", String((view.page - 1) * view.size));
    }
    return params.toString();
  }

  /* ------------------------------------------------------------------ */
  /* Data                                                                */
  /* ------------------------------------------------------------------ */
  async function safeApi(path) {
    try {
      return await api(path, { auth: true });
    } catch (error) {
      return { status: 0, data: { message: "Could not reach the server. Check your connection and try again." } };
    }
  }

  async function ensureCatalog() {
    if (rp.catalog) return true;
    const result = await safeApi("/api/v1/reports/catalog");
    if (result.status !== 200) return false;
    rp.catalog = result.data.data;
    return true;
  }

  async function ensureOptions() {
    if (rp.options) return;
    const result = await safeApi("/api/v1/reports/filter-options");
    // Not fatal: without it the dropdown filters just offer "All".
    rp.options = result.status === 200 ? result.data.data : {};
  }

  /* ------------------------------------------------------------------ */
  /* Small view helpers                                                  */
  /* ------------------------------------------------------------------ */
  function emptyState(text, extra) {
    return `<div class="empty-state">
      <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M3 7l3-4h12l3 4"/><path d="M3 12h5a2 2 0 0 0 4 0h5"/></svg>
      <p class="empty-state-text">${text}</p>${extra || ""}
    </div>`;
  }

  function errorState(message, actionAttr, actionLabel) {
    return `<div class="rp-error" role="alert">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12.5"/><line x1="12" y1="16" x2="12" y2="16.1"/></svg>
      <div><strong>${esc(message)}</strong></div>
      <button type="button" class="outline" ${actionAttr}>${esc(actionLabel)}</button>
    </div>`;
  }

  function categoryLabel(key) {
    const category = (rp.catalog.categories || []).find((c) => c.key === key);
    return category ? category.label : key;
  }

  function pill(value) {
    const raw = String(value);
    const kind = GOOD.has(raw) ? " good" : BAD.has(raw) ? " bad" : "";
    return `<span class="status-pill${kind}">${esc(humanize(raw))}</span>`;
  }

  function cellHtml(column, value) {
    if (value === null || value === undefined || value === "") return `<span class="rp-null">&mdash;</span>`;
    switch (column.kind) {
      case "number":
        return esc(Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 }));
      case "money":
        return esc(Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
      case "datetime":
        return esc(fmt(value));
      case "status":
        return pill(value);
      default:
        return esc(value);
    }
  }

  const alignClass = (column) => (column.kind === "number" || column.kind === "money" ? "rp-num" : "");

  /* ------------------------------------------------------------------ */
  /* Landing: summary cards + report list                                */
  /* ------------------------------------------------------------------ */
  const KPI_CLASSES = ["kpi-a", "kpi-b", "kpi-c", "kpi-d", "kpi-e", "kpi-a"];

  function summaryHtml(metrics) {
    if (!metrics.length) return "";
    return `<div class="kpi-grid rp-kpis" aria-label="Summary">${metrics
      .map((metric, index) => {
        const params = new URLSearchParams(metric.filters || {}).toString();
        const href = `#reports/${encodeURIComponent(metric.report)}${params ? "?" + params : ""}`;
        return `<a class="kpi-card ${KPI_CLASSES[index % KPI_CLASSES.length]} rp-kpi" href="${esc(href)}" title="Open the report behind this number">
          <span class="kpi-label"><span class="kpi-dot"></span>${esc(metric.label)}</span>
          <strong>${esc(Number(metric.value).toLocaleString())}</strong>
          ${metric.hint ? `<span class="rp-kpi-hint">${esc(metric.hint)}</span>` : `<span class="rp-kpi-hint">&nbsp;</span>`}
        </a>`;
      })
      .join("")}</div>`;
  }

  function summarySkeleton() {
    return `<div class="kpi-grid rp-kpis" aria-hidden="true">${[0, 1, 2, 3, 4]
      .map(() => `<div class="kpi-card rp-kpi-skeleton"><div class="skeleton-row"></div><div class="skeleton-row"></div></div>`)
      .join("")}</div>`;
  }

  async function loadSummary(mySeq) {
    const holder = document.getElementById("rp-summary");
    if (!holder) return;
    holder.innerHTML = summarySkeleton();
    const result = await safeApi("/api/v1/reports/summary");
    if (mySeq !== rp.seq || !document.getElementById("rp-summary")) return;
    if (result.status !== 200) {
      document.getElementById("rp-summary").innerHTML = errorState(
        result.data.message || "The summary could not be loaded.",
        'data-rp-action="retry-summary"',
        "Retry"
      );
      return;
    }
    rp.summary = result.data.data;
    document.getElementById("rp-summary").innerHTML = summaryHtml(rp.summary.metrics);
  }

  function matchesQuery(report, query) {
    if (!query) return true;
    const haystack = `${report.title} ${report.description} ${categoryLabel(report.category)}`.toLowerCase();
    return query
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
      .every((token) => haystack.includes(token));
  }

  function listHtml() {
    const all = rp.catalog.reports;
    const visible = all.filter((r) => (rp.category === "all" || r.category === rp.category) && matchesQuery(r, rp.query));
    if (!visible.length) {
      return emptyState(
        rp.query ? `No reports match &ldquo;${esc(rp.query)}&rdquo;.` : "No reports in this category.",
        rp.query || rp.category !== "all"
          ? `<button type="button" class="outline" data-rp-action="clear-search">Show all reports</button>`
          : ""
      );
    }
    const groups = rp.catalog.categories
      .map((category) => ({ category, items: visible.filter((r) => r.category === category.key) }))
      .filter((group) => group.items.length);
    return groups
      .map(
        (group) => `<section class="rp-group" aria-label="${esc(group.category.label)}">
        ${rp.category === "all" ? `<h3 class="rp-group-title">${esc(group.category.label)}<span>${esc(group.category.description)}</span></h3>` : ""}
        <ul class="rp-list">${group.items
          .map(
            (report) => `<li><a class="rp-item" href="#reports/${encodeURIComponent(report.key)}">
              <span class="rp-item-main"><strong>${esc(report.title)}</strong><span class="rp-item-desc">${esc(report.description)}</span></span>
              <span class="rp-item-go" aria-hidden="true">Open &rarr;</span>
            </a></li>`
          )
          .join("")}</ul>
      </section>`
      )
      .join("");
  }

  function tabsHtml() {
    const counts = {};
    for (const report of rp.catalog.reports) counts[report.category] = (counts[report.category] || 0) + 1;
    const tab = (key, label, count) =>
      `<button type="button" class="tab${rp.category === key ? " on" : ""}" data-rp-action="tab" data-category="${esc(key)}" aria-pressed="${rp.category === key}">${esc(label)} <span class="rp-tab-count">${count}</span></button>`;
    return (
      tab("all", "All reports", rp.catalog.reports.length) +
      rp.catalog.categories.map((c) => tab(c.key, c.label.replace(/ Reports$/, ""), counts[c.key] || 0)).join("")
    );
  }

  function renderListRegion() {
    const list = document.getElementById("rp-list");
    const tabs = document.getElementById("rp-tabs");
    if (list) list.innerHTML = listHtml();
    if (tabs) tabs.innerHTML = tabsHtml();
  }

  function renderLanding() {
    const mySeq = ++rp.seq;
    rp.view = null;
    rp.spec = null;
    if (!rp.catalog.reports.length) {
      root().innerHTML = emptyState("No reports are available for your role.");
      finishRender();
      return;
    }
    root().innerHTML = `
      <p class="rp-intro">Run reports on your organisation's employees, companies, assets and suppliers, filter and sort the results, and export them to CSV. You only see reports your role is allowed to run.</p>
      <div id="rp-summary"></div>
      <div class="rp-tools">
        <div class="rp-tabs" id="rp-tabs" role="group" aria-label="Report categories"></div>
        <div class="rp-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="search" id="rp-search" placeholder="Search reports&hellip;" aria-label="Search reports" value="${esc(rp.query)}" autocomplete="off" />
        </div>
      </div>
      <div id="rp-list"></div>`;
    renderListRegion();
    finishRender();
    loadSummary(mySeq);
  }

  /* ------------------------------------------------------------------ */
  /* Report view                                                         */
  /* ------------------------------------------------------------------ */
  function optionHtml(value, label, selected) {
    return `<option value="${esc(value)}"${selected ? " selected" : ""}>${esc(label)}</option>`;
  }

  function filterControl(filter, current) {
    const id = `rp-f-${filter.name}`;
    const value = current || "";
    let control;
    if (filter.kind === "text") {
      control = `<input id="${id}" type="search" value="${esc(value)}" placeholder="${esc(filter.placeholder || "")}" maxlength="100" autocomplete="off" />`;
    } else if (filter.kind === "date") {
      control = `<input id="${id}" type="date" value="${esc(value)}" />`;
    } else if (filter.kind === "select") {
      control = `<select id="${id}">${filter.options.map((o) => optionHtml(o.value, o.label, o.value === value)).join("")}</select>`;
    } else if (filter.kind === "company") {
      const companies = (rp.options && rp.options.companies) || [];
      if (companies.length <= 1) return ""; // nothing to choose between
      const known = companies.some((c) => String(c.id) === value);
      control = `<select id="${id}">${optionHtml("", "All companies", !value)}${companies
        .map((c) => optionHtml(c.id, c.name, String(c.id) === value))
        .join("")}${value && !known ? optionHtml(value, `Company ${value}`, true) : ""}</select>`;
    } else {
      // "source": distinct values from the caller's own data
      const values = (rp.options && rp.options[filter.source]) || [];
      const known = !value || values.includes(value);
      control = `<select id="${id}">${optionHtml("", "All", !value)}${values.map((v) => optionHtml(v, v, v === value)).join("")}${known ? "" : optionHtml(value, value, true)}</select>`;
    }
    return `<label class="rp-field" for="${id}">${esc(filter.label)}${control}</label>`;
  }

  function filterSummaryText(spec, filters) {
    const parts = [];
    for (const filter of spec.filters) {
      const value = filters[filter.name];
      if (!value) continue;
      let shown = value;
      if (filter.kind === "select") {
        const option = filter.options.find((o) => o.value === value);
        if (option) shown = option.label;
      } else if (filter.kind === "company") {
        const company = ((rp.options && rp.options.companies) || []).find((c) => String(c.id) === value);
        if (company) shown = company.name;
      }
      parts.push(`${filter.label}: ${shown}`);
    }
    return parts.length ? parts.join(" · ") : "None";
  }

  function renderReportShell(spec, view) {
    const hasDates = spec.filters.some((f) => f.kind === "date");
    const controls = spec.filters.map((f) => filterControl(f, view.filters[f.name])).join("");
    root().innerHTML = `
      <nav class="rp-crumbs rp-noprint" aria-label="Breadcrumb"><a href="#reports">&larr; All reports</a><span aria-hidden="true">/</span><span>${esc(categoryLabel(spec.category))}</span></nav>
      <header class="rp-head">
        <h3>${esc(spec.title)}</h3>
        <p>${esc(spec.description)}</p>
        ${spec.note ? `<p class="hint rp-note">${esc(spec.note)}</p>` : ""}
      </header>
      ${
        controls
          ? `<form id="rp-filters" class="filter-panel rp-filters rp-noprint" novalidate>
              <div class="rp-filter-grid">${controls}</div>
              ${hasDates ? `<p class="hint rp-date-hint">Dates are matched in UTC and include the whole of the &ldquo;to&rdquo; day.</p>` : ""}
              <div class="actions">
                <button type="submit" class="primary" id="rp-apply">${icon("search")}Apply filters</button>
                <button type="button" class="outline" data-rp-action="reset">${icon("close")}Reset</button>
              </div>
            </form>`
          : ""
      }
      <div class="rp-print-meta" id="rp-print-meta"></div>
      <div class="rp-resultbar">
        <div class="rp-count" id="rp-count" aria-live="polite">Loading&hellip;</div>
        <div class="rp-bar-actions rp-noprint">
          <button type="button" class="outline" id="rp-export" data-rp-action="export" disabled>${icon("download")}Export CSV</button>
          <button type="button" class="outline" id="rp-print" data-rp-action="print">${icon("note")}Print</button>
        </div>
      </div>
      <div id="rp-table" class="table-scroll rp-table-wrap" aria-busy="true">${skeletonTable()}</div>
      <div id="rp-pager" class="rp-pager rp-noprint"></div>`;
  }

  function resultTableHtml(spec, data, view) {
    const head = spec.columns
      .map((column) => {
        const sorted = column.sortable && view.sortBy === column.key;
        const aria = column.sortable ? ` aria-sort="${sorted ? (view.sortDir === "asc" ? "ascending" : "descending") : "none"}"` : "";
        const label = column.sortable
          ? `<button type="button" class="rp-sort" data-rp-action="sort" data-sort="${esc(column.key)}" title="Sort by ${esc(column.label)}">${esc(column.label)}<span class="rp-sort-ind" aria-hidden="true">${sorted ? (view.sortDir === "asc" ? "▲" : "▼") : ""}</span></button>`
          : esc(column.label);
        return `<th scope="col" class="${alignClass(column)}"${aria}>${label}</th>`;
      })
      .join("");
    const body = data.items
      .map((row) => `<tr>${spec.columns.map((c) => `<td class="${alignClass(c)}">${cellHtml(c, row[c.key])}</td>`).join("")}</tr>`)
      .join("");
    return `<table class="rp-table"><caption class="rp-sr">${esc(spec.title)}</caption><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function pagerHtml(data, view) {
    const pages = Math.max(1, Math.ceil(data.total / view.size));
    const from = data.total ? data.offset + 1 : 0;
    const to = data.offset + data.items.length;
    return `
      <div class="rp-pager-info">Showing <strong>${from.toLocaleString()}&ndash;${to.toLocaleString()}</strong> of <strong>${data.total.toLocaleString()}</strong></div>
      <div class="rp-pager-controls">
        <label class="rp-size">Rows per page
          <select id="rp-size" aria-label="Rows per page">${PAGE_SIZES.map((n) => optionHtml(n, n, n === view.size)).join("")}</select>
        </label>
        <button type="button" class="outline" data-rp-action="prev" ${view.page <= 1 ? "disabled" : ""}>&larr; Previous</button>
        <span class="rp-page">Page ${view.page.toLocaleString()} of ${pages.toLocaleString()}</span>
        <button type="button" class="outline" data-rp-action="next" ${data.has_more ? "" : "disabled"}>Next &rarr;</button>
      </div>`;
  }

  async function loadResults(mySeq) {
    const spec = rp.spec;
    const view = rp.view;
    const table = document.getElementById("rp-table");
    if (!table) return;
    table.setAttribute("aria-busy", "true");
    table.innerHTML = skeletonTable();
    const exportButton = document.getElementById("rp-export");
    if (exportButton) exportButton.disabled = true;

    const result = await safeApi(`/api/v1/reports/${encodeURIComponent(spec.key)}?${queryString(view, { paginate: true })}`);
    if (mySeq !== rp.seq || !document.getElementById("rp-table")) return; // superseded

    const count = document.getElementById("rp-count");
    const pager = document.getElementById("rp-pager");
    table.setAttribute("aria-busy", "false");

    if (result.status !== 200) {
      count.textContent = "Couldn't load results";
      pager.innerHTML = "";
      table.innerHTML = errorState(
        result.data.message || "The report could not be loaded.",
        'data-rp-action="retry"',
        "Retry"
      );
      return;
    }

    const data = result.data.data;
    // A bookmarked/typed page number past the end: jump to the last real page.
    if (!data.items.length && data.total > 0 && view.page > 1) {
      view.page = Math.max(1, Math.ceil(data.total / view.size));
      syncUrl(spec, view);
      loadResults(mySeq);
      return;
    }

    rp.lastData = data;
    rp.renderedAt = Date.now();
    count.innerHTML = `<strong>${data.total.toLocaleString()}</strong> matching record${data.total === 1 ? "" : "s"}`;
    document.getElementById("rp-print-meta").innerHTML = `<strong>${esc(spec.title)}</strong> &middot; Generated ${esc(
      new Date().toLocaleString()
    )} &middot; Filters: ${esc(filterSummaryText(spec, view.filters))} &middot; ${data.total.toLocaleString()} record${
      data.total === 1 ? "" : "s"
    }${data.total > data.items.length ? ` (rows ${(data.offset + 1).toLocaleString()}&ndash;${(data.offset + data.items.length).toLocaleString()} shown)` : ""}`;

    if (!data.items.length) {
      table.innerHTML = emptyState(
        Object.keys(view.filters).length ? "No records match these filters." : "There are no records to report on yet.",
        Object.keys(view.filters).length ? `<button type="button" class="outline" data-rp-action="reset">Reset filters</button>` : ""
      );
      pager.innerHTML = "";
      return;
    }
    table.innerHTML = resultTableHtml(spec, data, view);
    pager.innerHTML = pagerHtml(data, view);
    if (exportButton) {
      exportButton.disabled = false;
      exportButton.title = "Download every record matching the current filters as CSV";
    }
  }

  function openReport(spec, view) {
    rp.spec = spec;
    rp.view = view;
    const mySeq = ++rp.seq;
    renderReportShell(spec, view);
    syncUrl(spec, view);
    finishRender();
    loadResults(mySeq);
  }

  function readDraft(spec) {
    const out = {};
    for (const filter of spec.filters) {
      const el = document.getElementById(`rp-f-${filter.name}`);
      const value = el ? String(el.value || "").trim() : "";
      if (value) out[filter.name] = value;
    }
    return out;
  }

  function reload(resetPage) {
    if (!rp.spec || !rp.view) return;
    if (resetPage) rp.view.page = 1;
    syncUrl(rp.spec, rp.view);
    loadResults(++rp.seq);
  }

  /* ------------------------------------------------------------------ */
  /* Actions                                                             */
  /* ------------------------------------------------------------------ */
  function applyFilters() {
    const draft = readDraft(rp.spec);
    if (draft.date_from && draft.date_to && draft.date_from > draft.date_to) {
      toast("The 'from' date can't be after the 'to' date.", "bad");
      const el = document.getElementById("rp-f-date_from");
      if (el) el.focus();
      return;
    }
    rp.view.filters = draft;
    reload(true);
  }

  function resetFilters() {
    rp.view = { ...rp.view, filters: {}, sortBy: rp.spec.default_sort, sortDir: rp.spec.default_dir, page: 1 };
    for (const filter of rp.spec.filters) {
      const el = document.getElementById(`rp-f-${filter.name}`);
      if (el) el.value = "";
    }
    reload(false);
  }

  function toggleSort(column) {
    const view = rp.view;
    if (view.sortBy === column) {
      view.sortDir = view.sortDir === "asc" ? "desc" : "asc";
    } else {
      view.sortBy = column;
      view.sortDir = "asc";
    }
    reload(true);
  }

  async function exportCsv(button) {
    if (!state.accessToken) {
      toast("Access token required. Login first.", "bad");
      return;
    }
    const spec = rp.spec;
    const view = rp.view; // the APPLIED filters — what the table currently shows, not unsaved edits in the form
    const original = button.innerHTML;
    button.disabled = true;
    button.textContent = "Exporting…";
    try {
      const response = await fetch(withBasePath(`/api/v1/reports/${encodeURIComponent(spec.key)}/export?${queryString(view, { paginate: false })}`), {
        headers: { Authorization: `Bearer ${state.accessToken}`, Accept: "text/csv" },
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        toast(error.message || "The export failed.", "bad");
        return;
      }
      // downloadCsv() prepends its own UTF-8 BOM; strip the server's so the file doesn't start with two.
      const text = (await response.text()).replace(/^﻿/, "");
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/.exec(disposition);
      downloadCsv(match ? match[1] : `${spec.key}.csv`, text);
      const rows = response.headers.get("X-Report-Row-Count");
      toast(`Exported ${rows} row${rows === "1" ? "" : "s"}.`, "ok");
    } catch (error) {
      toast("Could not reach the server. The export was not downloaded.", "bad");
    } finally {
      button.innerHTML = original;
      button.disabled = !(rp.lastData && rp.lastData.total > 0);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Wiring (one set of delegated listeners on the root)                 */
  /* ------------------------------------------------------------------ */
  function ensureWired() {
    if (rp.wired) return;
    rp.wired = true;
    const host = root();

    host.addEventListener("click", (event) => {
      const target = event.target.closest("[data-rp-action]");
      if (!target || !host.contains(target)) return;
      const action = target.getAttribute("data-rp-action");
      switch (action) {
        case "tab":
          rp.category = target.getAttribute("data-category");
          renderListRegion();
          break;
        case "clear-search": {
          rp.query = "";
          rp.category = "all";
          const input = document.getElementById("rp-search");
          if (input) input.value = "";
          renderListRegion();
          break;
        }
        case "reset":
          resetFilters();
          break;
        case "sort":
          toggleSort(target.getAttribute("data-sort"));
          break;
        case "prev":
          if (rp.view.page > 1) {
            rp.view.page -= 1;
            reload(false);
          }
          break;
        case "next":
          rp.view.page += 1;
          reload(false);
          break;
        case "export":
          exportCsv(target);
          break;
        case "print":
          window.print();
          break;
        case "retry":
          reload(false);
          break;
        case "retry-summary":
          loadSummary(rp.seq);
          break;
        case "retry-catalog":
          rp.catalog = null;
          show(true);
          break;
        default:
      }
    });

    host.addEventListener("submit", (event) => {
      if (event.target.id !== "rp-filters") return;
      event.preventDefault();
      applyFilters();
    });

    host.addEventListener("input", (event) => {
      if (event.target.id !== "rp-search") return;
      rp.query = event.target.value.trim();
      renderListRegion();
    });

    host.addEventListener("change", (event) => {
      if (event.target.id !== "rp-size") return;
      rp.view.size = parseInt(event.target.value, 10) || DEFAULT_SIZE;
      reload(true);
    });

    // Only the Reports page is printed with the print layout (see styles.css).
    window.addEventListener("beforeprint", () => {
      if (rp.spec && !document.getElementById("section-reports").classList.contains("hidden")) document.body.classList.add("rp-printing");
    });
    window.addEventListener("afterprint", () => document.body.classList.remove("rp-printing"));
  }

  /* ------------------------------------------------------------------ */
  /* Entry point                                                         */
  /* ------------------------------------------------------------------ */
  function finishRender() {
    rp.rendered = true;
    rp.renderedAt = Date.now();
    rp.lastHash = location.hash;
  }

  // After a page reload, app.js activates the section named in the URL BEFORE
  // /auth/me has returned (so Overview doesn't flash first) — at that moment
  // there is an access token but no state.user yet. Wait for sign-in to
  // finish instead of giving up, or a refreshed deep link renders nothing.
  function whenSignedIn() {
    return new Promise((resolve) => {
      let tries = 0;
      const tick = () => {
        if (state.user) return resolve(true);
        if (!state.accessToken || ++tries > 200) return resolve(false); // signed out, or gave up after ~20s
        setTimeout(tick, 100);
      };
      tick();
    });
  }

  async function show(force) {
    if (typeof state === "undefined") return;
    if (!state.user) {
      if (!state.accessToken) return; // signed out
      const waiting = ++rp.seq;
      root().innerHTML = `<div class="rp-loading" aria-busy="true">${skeletonTable(4)}</div>`;
      const ready = await whenSignedIn();
      if (!ready || waiting !== rp.seq) return;
      force = true;
    }
    ensureWired();

    // A different user signed in without a page reload: nothing cached about
    // the previous one may be reused.
    if (rp.userId !== state.user.id) {
      rp.userId = state.user.id;
      rp.catalog = null;
      rp.options = null;
      rp.summary = null;
      rp.category = "all";
      rp.query = "";
      rp.rendered = false;
      force = true;
    }

    // Both Back/Forward and the nav click land here (and the nav click lands
    // twice: once directly, once via hashchange) — skip work that's already
    // done unless the view is stale or the URL actually changed.
    if (!force && rp.rendered && rp.lastHash === location.hash && Date.now() - rp.renderedAt < STALE_MS) return;

    const mySeq = ++rp.seq;
    if (!rp.catalog) {
      root().innerHTML = `<div class="rp-loading" aria-busy="true">${skeletonTable(4)}</div>`;
      const ok = await ensureCatalog();
      if (mySeq !== rp.seq) return;
      if (!ok) {
        root().innerHTML = errorState("The reports could not be loaded.", 'data-rp-action="retry-catalog"', "Retry");
        rp.rendered = false;
        return;
      }
    }

    const route = parseRoute();
    if (!route.key) {
      renderLanding();
      return;
    }

    const spec = rp.catalog.reports.find((r) => r.key === route.key);
    if (!spec) {
      root().innerHTML = `<nav class="rp-crumbs"><a href="#reports">&larr; All reports</a></nav>${emptyState(
        "This report doesn't exist or isn't available for your role."
      )}`;
      finishRender();
      return;
    }
    await ensureOptions();
    if (mySeq !== rp.seq) return;
    openReport(spec, viewFromParams(spec, route.params));
  }

  window.NexusSections = window.NexusSections || {};
  window.NexusSections["section-reports"] = () => show(false);
})();
