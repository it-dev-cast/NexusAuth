/* Master Management page.
 *
 * One page for every master. The dropdown at the top lists them all (grouped:
 * People, Assets, Suppliers) and only the chosen master's content is shown.
 *
 *   - "page" masters (Departments, Job Roles, Applications, Manufacturers,
 *     Models) already had full screens; those are the .mm-panel blocks in
 *     index.html, driven by app.js exactly as before. Choosing one just shows
 *     its panel.
 *   - "list" masters (Application Category, Supplier Category, Payment Terms)
 *     are drawn here, into #mm-generic, from /api/v1/master-data/<list>:
 *     search, status filter, paging, add, rename, describe, deactivate and
 *     reactivate.
 *
 * Which masters exist, their groups and counts come from the server
 * (GET /api/v1/master-data/catalog), so a master added there appears with no
 * change to this file.
 *
 * URL = state: #masters/<master>?q=&status=&size=&page=  (the old addresses
 * #departments, #job-roles, #applications, #manufacturers and #models still
 * work and open the same master). Changing the dropdown or a filter uses
 * replaceState; refresh, Back/Forward and shared links land on the same view.
 *
 * Loaded BEFORE app.js and touches none of app.js's bindings at load time.
 */
(function () {
  "use strict";

  const PAGE_SIZES = [10, 25, 50, 100];
  const DEFAULT_SIZE = 25;
  const STATUSES = [
    ["active", "Active"],
    ["inactive", "Inactive"],
    ["all", "All"],
  ];
  const ALIASES = {
    departments: "department",
    "job-roles": "job-role",
    applications: "application",
    manufacturers: "manufacturer",
    models: "asset-model",
  };
  const LAST_KEY = "nexusone.lastMaster";
  // Application Master has its own sidebar item and page, so it is not one of
  // the choices in the Master Management dropdown; when it is the master being
  // shown, the page drops the chooser and takes Application Master's own title.
  const SOLO_SLUG = "application";
  const SOLO_TITLE = "Application Master";
  const SOLO_SUBTITLE = "Applications your teams use, and who has access to each.";
  const SOLO_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/></svg>';
  const shell = { saved: null };
  const SEARCH_DEBOUNCE_MS = 250;

  const mm = {
    userId: null,
    catalog: null,
    spec: null, // catalog entry shown now
    view: null, // filters of the generic list
    data: null,
    form: null, // null | "new" | id being edited
    seq: 0,
    wired: false,
    timer: null,
  };

  const esc = (value) => escapeHtml(value == null ? "" : String(value));
  const select = () => document.getElementById("mm-select");
  const generic = () => document.getElementById("mm-generic");
  const optionHtml = (value, label, selected) =>
    `<option value="${esc(value)}"${selected ? " selected" : ""}>${esc(label)}</option>`;

  /* ------------------------------------------------------------------ */
  /* Routing                                                             */
  /* ------------------------------------------------------------------ */
  function parseRoute() {
    const raw = location.hash.replace(/^#/, "");
    const cut = raw.indexOf("?");
    const path = cut === -1 ? raw : raw.slice(0, cut);
    const params = new URLSearchParams(cut === -1 ? "" : raw.slice(cut + 1));
    const first = path.split("/")[0];
    let slug = null;
    if (ALIASES[first]) slug = ALIASES[first];
    else if (first === "masters" && path.split("/")[1]) {
      try {
        slug = decodeURIComponent(path.split("/")[1]);
      } catch (error) {
        slug = path.split("/")[1];
      }
    }
    return { slug, params };
  }

  function viewFromParams(params) {
    let status = params.get("status");
    if (!STATUSES.some(([value]) => value === status)) status = "active";
    let size = parseInt(params.get("size"), 10);
    if (!PAGE_SIZES.includes(size)) size = DEFAULT_SIZE;
    let page = parseInt(params.get("page"), 10);
    if (!(page >= 1)) page = 1;
    const sortDir = params.get("sort_dir") === "desc" ? "desc" : "asc";
    return { q: (params.get("q") || "").slice(0, 100), status, size, page, sortDir };
  }

  function hashFor(spec, view) {
    const params = new URLSearchParams();
    if (spec.kind === "list" && view) {
      if (view.q) params.set("q", view.q);
      if (view.status !== "active") params.set("status", view.status);
      if (view.sortDir !== "asc") params.set("sort_dir", view.sortDir);
      if (view.size !== DEFAULT_SIZE) params.set("size", String(view.size));
      if (view.page > 1) params.set("page", String(view.page));
    }
    const query = params.toString();
    return `#masters/${encodeURIComponent(spec.slug)}${query ? "?" + query : ""}`;
  }

  function syncUrl() {
    const hash = hashFor(mm.spec, mm.view);
    if (location.hash !== hash) history.replaceState(null, "", hash);
    if (window.syncMasterNav) window.syncMasterNav();
  }

  function listQuery(view) {
    const params = new URLSearchParams();
    params.set("status", view.status);
    if (view.q) params.set("search", view.q);
    params.set("sort_by", "name");
    params.set("sort_dir", view.sortDir);
    params.set("limit", String(view.size));
    params.set("offset", String((view.page - 1) * view.size));
    return params.toString();
  }

  /* ------------------------------------------------------------------ */
  /* Data                                                                */
  /* ------------------------------------------------------------------ */
  async function safeApi(path, options) {
    try {
      return await api(path, Object.assign({ auth: true }, options || {}));
    } catch (error) {
      return { status: 0, data: { message: "Could not reach the server. Check your connection and try again." } };
    }
  }

  async function loadCatalog() {
    const result = await safeApi("/api/v1/master-data/catalog");
    if (result.status !== 200) return false;
    mm.catalog = result.data.data;
    return true;
  }

  // The dropdowns on the Employee / Supplier / Application forms read these
  // lists, so refresh them after every change here.
  function afterChange() {
    if (typeof loadMasterDropdowns === "function") loadMasterDropdowns();
    loadCatalog().then(() => {
      if (mm.spec) updateDescription(mm.catalog.masters.find((m) => m.key === mm.spec.key) || mm.spec);
    });
  }

  /* ------------------------------------------------------------------ */
  /* The dropdown and the shell                                          */
  /* ------------------------------------------------------------------ */
  function renderSelect(currentKey) {
    const { groups, masters } = mm.catalog;
    select().innerHTML = groups
      .map((group) => {
        const items = masters.filter((m) => m.group === group && m.slug !== SOLO_SLUG);
        if (!items.length) return "";
        return `<optgroup label="${esc(group)}">${items.map((m) => optionHtml(m.slug, m.plural, m.key === currentKey)).join("")}</optgroup>`;
      })
      .join("");
  }

  function updateDescription(spec) {
    const el = document.getElementById("mm-description");
    if (!el) return;
    el.innerHTML = `${esc(spec.description)} <span class="mm-meta">Used in: ${esc(spec.used_by)} &middot; <strong>${spec.active_count}</strong> active of ${spec.total_count}</span>`;
  }

  // Header (breadcrumb, title, subtitle, icon) and chooser follow the master
  // on show: Application Master is its own page, everything else is Master Management.
  function applyShell(spec) {
    const section = document.getElementById("section-masters");
    if (!section) return;
    const crumb = section.querySelector(".breadcrumb-current");
    const title = section.querySelector(".page-header-text h2");
    const sub = section.querySelector(".page-header-text p");
    const icon = section.querySelector(".page-icon");
    if (!shell.saved && crumb && title && sub && icon) {
      shell.saved = { crumb: crumb.textContent, title: title.textContent, sub: sub.textContent, icon: icon.innerHTML };
    }
    const solo = spec.slug === SOLO_SLUG;
    section.classList.toggle("mm-solo", solo);
    if (!shell.saved) return;
    crumb.textContent = solo ? SOLO_TITLE : shell.saved.crumb;
    title.textContent = solo ? SOLO_TITLE : shell.saved.title;
    sub.textContent = solo ? SOLO_SUBTITLE : shell.saved.sub;
    icon.innerHTML = solo ? SOLO_ICON : shell.saved.icon;
  }

  function showPanel(spec) {
    document.querySelectorAll("#section-masters .mm-panel").forEach((panel) => panel.classList.add("hidden"));
    if (spec.kind === "page") {
      const panel = document.getElementById(`mm-panel-${spec.slug}`);
      if (panel) panel.classList.remove("hidden");
    } else {
      generic().classList.remove("hidden");
    }
  }

  /* ------------------------------------------------------------------ */
  /* A list master (drawn here)                                          */
  /* ------------------------------------------------------------------ */
  const statusPill = (active) => `<span class="status-pill">${active ? "Active" : "Inactive"}</span>`;

  function emptyState(text, extra) {
    return `<div class="empty-state">
      <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M3 7l3-4h12l3 4"/><path d="M3 12h5a2 2 0 0 0 4 0h5"/></svg>
      <p class="empty-state-text">${text}</p>${extra || ""}
    </div>`;
  }

  function errorState(message, action, label) {
    return `<div class="rp-error" role="alert">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12.5"/><line x1="12" y1="16" x2="12" y2="16.1"/></svg>
      <div><strong>${esc(message)}</strong></div>
      <button type="button" class="outline" data-mm-action="${action}">${esc(label)}</button>
    </div>`;
  }

  function renderGeneric() {
    const spec = mm.spec;
    const view = mm.view;
    generic().innerHTML = `
      <div class="card">
        <div class="card-head">
          <h3>${esc(spec.label)} master</h3>
          <div class="card-head-controls">
            <div class="mm-search">
              <label class="rp-sr" for="mm-search">Search ${esc(spec.plural)}</label>
              <input id="mm-search" type="search" class="search-input" maxlength="100" autocomplete="off" placeholder="Search ${esc(spec.plural.toLowerCase())}…" value="${esc(view.q)}" />
            </div>
            <label class="mm-status">Status
              <select id="mm-status">${STATUSES.map(([v, l]) => optionHtml(v, l, v === view.status)).join("")}</select>
            </label>
          </div>
          <button type="button" class="primary" data-mm-action="new">New ${esc(spec.label.toLowerCase())}</button>
        </div>
        <div id="mm-form-wrap"></div>
        <div id="mm-table" class="table-scroll" aria-busy="true">${skeletonTable()}</div>
        <div id="mm-pager" class="mm-pager"></div>
      </div>`;
    renderForm();
    loadItems();
  }

  function usageText(item) {
    return item.usage_count > 0
      ? `${item.usage_count} record${item.usage_count === 1 ? "" : "s"}`
      : '<span class="mm-null">—</span>';
  }

  function tableHtml(items) {
    const view = mm.view;
    const dir = view.sortDir === "asc" ? "desc" : "asc";
    const rows = items
      .map(
        (item) => `
        <tr>
          <td><strong>${esc(item.name)}</strong></td>
          <td>${item.description ? esc(item.description) : '<span class="mm-null">—</span>'}</td>
          <td>${usageText(item)}</td>
          <td>${statusPill(item.is_active)}</td>
          <td class="mm-actions">
            <button type="button" data-mm-action="edit" data-id="${item.id}">Edit</button>
            ${
              item.is_active
                ? `<button type="button" class="danger" data-mm-action="deactivate" data-id="${item.id}">Deactivate</button>`
                : `<button type="button" data-mm-action="reactivate" data-id="${item.id}">Reactivate</button>`
            }
          </td>
        </tr>`
      )
      .join("");
    return `<table><thead><tr>
      <th scope="col" aria-sort="${view.sortDir === "asc" ? "ascending" : "descending"}"><button type="button" class="mm-sort" data-mm-action="sort" data-dir="${dir}">Name <span aria-hidden="true">${view.sortDir === "asc" ? "▲" : "▼"}</span></button></th>
      <th scope="col">Description</th>
      <th scope="col">In use</th>
      <th scope="col">Status</th>
      <th scope="col">Actions</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  }

  function pagerHtml(data, view) {
    const pages = Math.max(1, Math.ceil(data.total / view.size));
    const from = data.total ? data.offset + 1 : 0;
    const to = data.offset + data.items.length;
    return `
      <span class="mm-pager-info">Showing <strong>${from}&ndash;${to}</strong> of <strong>${data.total}</strong></span>
      <span class="mm-pager-controls">
        <label class="mm-size">Rows <select id="mm-size" aria-label="Rows per page">${PAGE_SIZES.map((n) => optionHtml(n, n, n === view.size)).join("")}</select></label>
        <button type="button" class="outline" data-mm-action="prev" ${view.page <= 1 ? "disabled" : ""}>&larr; Previous</button>
        <span>Page ${view.page} of ${pages}</span>
        <button type="button" class="outline" data-mm-action="next" ${data.has_more ? "" : "disabled"}>Next &rarr;</button>
      </span>`;
  }

  async function loadItems() {
    const spec = mm.spec;
    const view = mm.view;
    const mySeq = ++mm.seq;
    const table = document.getElementById("mm-table");
    if (!table) return;
    table.setAttribute("aria-busy", "true");
    table.innerHTML = skeletonTable();
    const result = await safeApi(`/api/v1/master-data/${encodeURIComponent(spec.slug)}?${listQuery(view)}`);
    if (mySeq !== mm.seq || !document.getElementById("mm-table")) return;
    const pager = document.getElementById("mm-pager");
    table.setAttribute("aria-busy", "false");
    if (result.status !== 200) {
      pager.innerHTML = "";
      table.innerHTML = errorState(result.data.message || "The list could not be loaded.", "retry", "Retry");
      return;
    }
    const data = result.data.data;
    if (data.total > 0 && data.items.length === 0 && view.page > 1) {
      view.page = Math.max(1, Math.ceil(data.total / view.size));
      syncUrl();
      loadItems();
      return;
    }
    mm.data = data;
    syncUrl();
    if (!data.items.length) {
      const filtered = view.q || view.status !== "active";
      table.innerHTML = emptyState(
        filtered
          ? `No ${esc(spec.plural.toLowerCase())} match these filters.`
          : `There are no ${esc(spec.plural.toLowerCase())} yet. Use “New ${esc(spec.label.toLowerCase())}” to add the first one.`,
        filtered ? '<button type="button" class="outline" data-mm-action="reset">Reset filters</button>' : ""
      );
      pager.innerHTML = "";
      return;
    }
    table.innerHTML = tableHtml(data.items);
    pager.innerHTML = pagerHtml(data, view);
  }

  function renderForm() {
    const wrap = document.getElementById("mm-form-wrap");
    if (!wrap) return;
    if (mm.form === null) {
      wrap.innerHTML = "";
      return;
    }
    const spec = mm.spec;
    const editing = mm.form !== "new";
    const item = editing && mm.data ? mm.data.items.find((i) => i.id === mm.form) : null;
    if (editing && !item) {
      mm.form = null;
      wrap.innerHTML = "";
      return;
    }
    const locked = editing && item.usage_count > 0;
    wrap.innerHTML = `
      <form id="mm-form" class="entity-form" novalidate>
        <p class="hint" style="margin:0 0 12px;"><span class="required-mark">*</span> Required</p>
        <div class="form-grid">
          <label>Name<span class="required-mark">*</span>
            <input id="mm-f-name" maxlength="150" required value="${esc(editing ? item.name : "")}" ${locked ? "disabled" : ""} />
          </label>
          <label>Description (optional)
            <input id="mm-f-description" maxlength="500" value="${esc(editing ? item.description || "" : "")}" />
          </label>
        </div>
        ${
          locked
            ? `<p class="hint">This value is used by ${item.usage_count} record${item.usage_count === 1 ? "" : "s"}, so its name can't be changed. To rename it, deactivate it and add a new value.</p>`
            : ""
        }
        <div class="actions">
          <button type="submit" class="primary" id="mm-form-submit">${editing ? "Save changes" : `Create ${esc(spec.label.toLowerCase())}`}</button>
          <button type="button" class="outline" data-mm-action="cancel">Cancel</button>
        </div>
      </form>`;
    const input = document.getElementById(locked ? "mm-f-description" : "mm-f-name");
    if (input) input.focus();
  }

  async function submitForm() {
    const spec = mm.spec;
    const editing = mm.form !== "new";
    const item = editing ? mm.data.items.find((i) => i.id === mm.form) : null;
    const nameEl = document.getElementById("mm-f-name");
    const name = nameEl.value.trim();
    if (!name && !nameEl.disabled) {
      toast("Name is required.", "bad");
      nameEl.focus();
      return;
    }
    const description = document.getElementById("mm-f-description").value.trim();
    let body;
    if (!editing) {
      body = { name, description: description || null };
    } else {
      body = {};
      if (!nameEl.disabled && name !== item.name) body.name = name;
      if (description !== (item.description || "")) body.description = description || null;
      if (!Object.keys(body).length) {
        toast("Nothing to save — no changes.", "ok");
        return;
      }
    }
    const submit = document.getElementById("mm-form-submit");
    submit.disabled = true;
    const path = `/api/v1/master-data/${encodeURIComponent(spec.slug)}${editing ? "/" + item.id : ""}`;
    const result = await safeApi(path, { method: editing ? "PUT" : "POST", body });
    if (result.status === 200 || result.status === 201) {
      toast(editing ? `${spec.label} updated.` : `${spec.label} created.`, "ok");
      mm.form = null;
      afterChange();
      loadItems();
      renderForm();
    } else if (submit.isConnected) {
      submit.disabled = false; // api() already showed the server's message
    }
  }

  async function changeActive(id, activate) {
    const spec = mm.spec;
    const item = mm.data.items.find((i) => i.id === id);
    if (!item) return;
    if (!activate) {
      const note =
        item.usage_count > 0
          ? ` ${item.usage_count} record${item.usage_count === 1 ? "" : "s"} already use it and will keep it.`
          : "";
      if (!(await confirmModal(`Deactivate “${item.name}”? It will no longer be offered in dropdowns.${note}`))) return;
    }
    const path = `/api/v1/master-data/${encodeURIComponent(spec.slug)}/${id}${activate ? "/reactivate" : ""}`;
    const result = await safeApi(path, { method: activate ? "PATCH" : "DELETE" });
    if (result.status === 200) {
      toast(`${item.name} ${activate ? "reactivated" : "deactivated"}.`, "ok");
      afterChange();
      loadItems();
    }
  }

  /* ------------------------------------------------------------------ */
  /* Events (wired once)                                                 */
  /* ------------------------------------------------------------------ */
  function ensureWired() {
    if (mm.wired) return;
    mm.wired = true;
    select().addEventListener("change", () => {
      const spec = mm.catalog.masters.find((m) => m.slug === select().value);
      if (!spec) return;
      try {
        localStorage.setItem(LAST_KEY, spec.slug);
      } catch (error) {
        /* remembering the choice is optional */
      }
      mm.form = null;
      chooseMaster(spec, new URLSearchParams());
    });

    const el = generic();
    el.addEventListener("input", (event) => {
      if (event.target.id !== "mm-search") return;
      clearTimeout(mm.timer);
      const value = event.target.value;
      mm.timer = setTimeout(() => {
        mm.view.q = value.trim();
        mm.view.page = 1;
        loadItems();
      }, SEARCH_DEBOUNCE_MS);
    });
    el.addEventListener("change", (event) => {
      if (event.target.id === "mm-status") {
        mm.view.status = event.target.value;
        mm.view.page = 1;
        loadItems();
      } else if (event.target.id === "mm-size") {
        mm.view.size = Number(event.target.value);
        mm.view.page = 1;
        loadItems();
      }
    });
    el.addEventListener("submit", (event) => {
      if (event.target.id !== "mm-form") return;
      event.preventDefault();
      submitForm();
    });
    el.addEventListener("click", (event) => {
      const button = event.target.closest("[data-mm-action]");
      if (!button || button.disabled) return;
      const action = button.getAttribute("data-mm-action");
      const id = Number(button.getAttribute("data-id"));
      if (action === "new") {
        mm.form = "new";
        renderForm();
      } else if (action === "edit") {
        mm.form = id;
        renderForm();
      } else if (action === "cancel") {
        mm.form = null;
        renderForm();
      } else if (action === "deactivate") {
        changeActive(id, false);
      } else if (action === "reactivate") {
        changeActive(id, true);
      } else if (action === "sort") {
        mm.view.sortDir = button.getAttribute("data-dir");
        mm.view.page = 1;
        loadItems();
      } else if (action === "prev") {
        mm.view.page = Math.max(1, mm.view.page - 1);
        loadItems();
      } else if (action === "next") {
        mm.view.page += 1;
        loadItems();
      } else if (action === "reset") {
        mm.view = viewFromParams(new URLSearchParams());
        renderGeneric();
      } else if (action === "retry") {
        loadItems();
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Entry                                                               */
  /* ------------------------------------------------------------------ */
  function chooseMaster(spec, params) {
    mm.spec = spec;
    mm.view = spec.kind === "list" ? viewFromParams(params) : null;
    select().value = spec.slug;
    updateDescription(spec);
    applyShell(spec);
    showPanel(spec);
    if (spec.kind === "list") renderGeneric();
    syncUrl();
  }

  function whenSignedIn() {
    return new Promise((resolve) => {
      let tries = 0;
      const tick = () => {
        if (state.user) return resolve(true);
        if (!state.accessToken || ++tries > 200) return resolve(false);
        setTimeout(tick, 100);
      };
      tick();
    });
  }

  async function show(force) {
    if (typeof state === "undefined") return;
    if (!state.user) {
      if (!state.accessToken) return;
      const ready = await whenSignedIn();
      if (!ready) return;
    }
    ensureWired();
    if (mm.userId !== state.user.id) {
      mm.userId = state.user.id;
      mm.catalog = null;
      mm.spec = null;
    }
    // Master data is managed by administrators; the sidebar hides this page
    // from everyone else and the server refuses their writes too.
    if (state.user.role !== "admin") {
      generic().classList.remove("hidden");
      generic().innerHTML = `<div class="card">${emptyState("Master Management is for administrators.")}</div>`;
      return;
    }
    const mySeq = ++mm.seq;
    if (!mm.catalog) {
      if (!(await loadCatalog())) {
        generic().classList.remove("hidden");
        generic().innerHTML = `<div class="card">${errorState("Master data could not be loaded.", "retry", "Retry")}</div>`;
        return;
      }
      if (mySeq !== mm.seq) return;
    }
    const route = parseRoute();
    let slug = route.slug;
    if (!slug) {
      try {
        slug = localStorage.getItem(LAST_KEY);
        if (slug === SOLO_SLUG) slug = null; // reached through its own sidebar item, not as the "last master"
      } catch (error) {
        slug = null;
      }
    }
    let spec = mm.catalog.masters.find((m) => m.slug === slug) || mm.catalog.masters[0];
    // Same master and URL as already shown (the nav click lands twice): leave it be.
    if (!force && mm.spec && mm.spec.key === spec.key && select().options.length && location.hash === hashFor(spec, mm.view)) return;
    renderSelect(spec.key);
    mm.form = null;
    chooseMaster(spec, route.params);
  }

  window.NexusSections = window.NexusSections || {};
  window.NexusSections["section-masters"] = () => show(false);
})();
