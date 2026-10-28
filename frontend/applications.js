/* Application Master.
 *
 * The "Application" master on the Master Management page: list with search,
 * status/category filters and paging; add / edit; activate / deactivate; and
 * per-application access management (which employees have it). The Employee
 * details drawer reuses renderEmployeeApps() for the employee-side view.
 *
 * It records who is meant to use an application. It does not sign anyone in
 * to, or provision accounts in, the application itself.
 *
 * All data comes from the existing API:
 *   GET/POST/PUT/DELETE/PATCH /api/v1/applications...   (master list)
 *   GET/POST/DELETE /api/v1/applications/{id}/access... (admin only)
 *   GET /api/v1/employees/{id}/applications             (employee view)
 * Who may do what is decided by the server; this file only decides what to
 * offer (can("application", ...), can("application_access", ...)).
 *
 * Loaded BEFORE app.js. It uses app.js helpers (api, toast, confirmModal,
 * fmt, ...) only inside functions, never at load time.
 */
(function () {
  "use strict";

  const PAGE_SIZES = [10, 25, 50, 100];
  const SEARCH_DEBOUNCE_MS = 250;
  const NO_DATE = '<span class="mm-null" title="Granted before access dates were recorded">Before tracking</span>';

  const am = {
    q: "",
    status: "all",
    category: "",
    size: 25,
    page: 1,
    data: null,
    seq: 0,
    timer: null,
    wired: false,
    access: null, // { app, q, page, size, data, seq, picks: Map, grantQ, grantSeq, changed }
  };

  const el = (id) => document.getElementById(id);
  const esc = (value) => escapeHtml(value == null ? "" : String(value));
  const mono = (value) => `<span class="text-mono-id">${esc(value)}</span>`;
  const dash = '<span class="mm-null">—</span>';

  function statusPill(active) {
    return `<span class="status-pill ${active ? "good" : "bad"}">${active ? "Active" : "Inactive"}</span>`;
  }
  // Date only in the table (the full timestamp is the tooltip).
  function when(value) {
    if (!value) return dash;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return esc(fmt(value));
    return `<span title="${esc(date.toLocaleString())}">${esc(date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }))}</span>`;
  }
  function canManageApplications() {
    return can("application", "write");
  }
  function canManageAccess() {
    return can("application_access", "write");
  }
  function errorState(message, action, label) {
    return `<div class="empty-state am-error" role="alert">
      <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12.5"/><line x1="12" y1="16" x2="12" y2="16.1"/></svg>
      <p class="empty-state-text">${esc(message)}</p>
      <button type="button" class="outline" data-am-action="${action}">${esc(label)}</button>
    </div>`;
  }
  function emptyState(message, extra) {
    return `<div class="empty-state">
      <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M3 7l3-4h12l3 4"/><path d="M3 12h5a2 2 0 0 0 4 0h5"/></svg>
      <p class="empty-state-text">${message}</p>${extra || ""}
    </div>`;
  }
  // api() already toasts failures; a network error comes back as a rejected fetch.
  async function safeApi(path, options) {
    try {
      return await api(path, { auth: true, ...options });
    } catch (error) {
      toast("Could not reach the server.", "bad");
      return { status: 0, data: {} };
    }
  }
  function pagerHtml(data, size, page, prefix) {
    const pages = Math.max(1, Math.ceil(data.total / size));
    const from = data.total ? data.offset + 1 : 0;
    const to = data.offset + data.items.length;
    return `
      <span class="mm-pager-info">Showing <strong>${from}&ndash;${to}</strong> of <strong>${data.total}</strong></span>
      <span class="mm-pager-controls">
        <label class="mm-size">Rows <select data-${prefix}-size aria-label="Rows per page">${PAGE_SIZES.map((n) => `<option value="${n}"${n === size ? " selected" : ""}>${n}</option>`).join("")}</select></label>
        <button type="button" class="outline" data-${prefix}-page="prev" ${page <= 1 ? "disabled" : ""}>&larr; Previous</button>
        <span>Page ${page} of ${pages}</span>
        <button type="button" class="outline" data-${prefix}-page="next" ${data.has_more ? "" : "disabled"}>Next &rarr;</button>
      </span>`;
  }

  /* ---------------- the master list ---------------- */

  function listQuery(extra) {
    const params = new URLSearchParams({
      limit: String(am.size),
      offset: String((am.page - 1) * am.size),
      status: am.status,
      ...extra,
    });
    if (am.q.trim()) params.set("search", am.q.trim());
    if (am.category) params.set("category", am.category);
    return params.toString();
  }

  function rowHtml(a) {
    const manage = canManageApplications();
    const access = canManageAccess();
    const link = a.url ? ` <a class="am-url" href="${esc(a.url)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(a.name)} in a new tab" title="${esc(a.url)}">${icon("link")}</a>` : "";
    return `<tr class="${a.is_active ? "" : "am-row-inactive"}" data-id="${a.id}">
      <td><strong>${esc(a.name)}</strong>${link}</td>
      <td>${mono(a.code)}</td>
      <td>${a.category ? esc(a.category) : dash}</td>
      <td>${access ? `<button type="button" class="am-count" data-am-action="access" data-id="${a.id}" title="Manage who has access">${a.employee_count ?? 0}</button>` : a.employee_count ?? 0}</td>
      <td>${statusPill(a.is_active)}</td>
      <td>${when(a.updated_at)}</td>
      <td class="am-actions"><div class="am-actions-row">
        <button type="button" data-am-action="view" data-id="${a.id}">${icon("view")}View</button>
        ${manage ? `<button type="button" data-am-action="edit" data-id="${a.id}">${icon("edit")}Edit</button>` : ""}
        ${access ? `<button type="button" data-am-action="access" data-id="${a.id}">${icon("access")}Access</button>` : ""}
        ${
          manage
            ? a.is_active
              ? `<button type="button" class="danger" data-am-action="deactivate" data-id="${a.id}">${icon("deactivate")}Deactivate</button>`
              : `<button type="button" data-am-action="activate" data-id="${a.id}">${icon("reactivate")}Activate</button>`
            : ""
        }
      </div></td>
    </tr>`;
  }

  function tableHtml(items) {
    return `<table class="am-table"><thead><tr>
      <th scope="col">Application Name</th>
      <th scope="col">Application Code</th>
      <th scope="col">Category</th>
      <th scope="col">Assigned Employees</th>
      <th scope="col">Status</th>
      <th scope="col">Updated At</th>
      <th scope="col">Actions</th>
    </tr></thead><tbody>${items.map(rowHtml).join("")}</tbody></table>`;
  }

  async function load() {
    const tableEl = el("applications-table");
    const pagerEl = el("applications-pager");
    if (!tableEl) return;
    const mySeq = ++am.seq;
    tableEl.setAttribute("aria-busy", "true");
    tableEl.innerHTML = skeletonTable();
    const result = await safeApi(`/api/v1/applications?${listQuery()}`);
    if (mySeq !== am.seq) return;
    tableEl.setAttribute("aria-busy", "false");
    if (result.status !== 200) {
      pagerEl.innerHTML = "";
      tableEl.innerHTML = errorState(result.data.message || "The applications could not be loaded.", "retry", "Retry");
      return;
    }
    const data = result.data.data;
    if (data.total > 0 && !data.items.length && am.page > 1) {
      am.page = Math.max(1, Math.ceil(data.total / am.size));
      return load();
    }
    am.data = data;
    if (!data.items.length) {
      const filtered = am.q.trim() || am.category || am.status !== "all";
      tableEl.innerHTML = emptyState(
        filtered
          ? "No applications match these filters."
          : "No applications have been added yet." + (canManageApplications() ? " Use “Add Application” to register the first one." : ""),
        filtered ? '<button type="button" class="outline" data-am-action="reset">Reset filters</button>' : ""
      );
      pagerEl.innerHTML = "";
      return;
    }
    tableEl.innerHTML = tableHtml(data.items);
    pagerEl.innerHTML = pagerHtml(data, am.size, am.page, "am");
  }

  async function loadCategories() {
    const select = el("applications-category-filter");
    if (!select) return;
    const [inUse, listed] = await Promise.all([
      safeApi("/api/v1/applications/categories"),
      safeApi("/api/v1/master-data/application_category/options"),
    ]);
    const names = new Set();
    if (inUse.status === 200) (inUse.data.data || []).forEach((c) => names.add(c));
    if (listed.status === 200) ((listed.data.data || {}).items || []).forEach((i) => names.add(i.name));
    const sorted = [...names].sort((a, b) => a.localeCompare(b));
    select.innerHTML = '<option value="">All categories</option>' + sorted.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    if (am.category && sorted.some((c) => c.toLowerCase() === am.category.toLowerCase())) select.value = sorted.find((c) => c.toLowerCase() === am.category.toLowerCase());
    else am.category = "";
  }

  function findLoaded(id) {
    return ((am.data && am.data.items) || []).find((a) => String(a.id) === String(id));
  }

  /* ---------------- add / edit ---------------- */

  function clearFormErrors() {
    el("application-form-error").classList.add("hidden");
    el("application-form-error").textContent = "";
    el("form-application").querySelectorAll("[data-error-for]").forEach((s) => (s.textContent = ""));
    el("form-application").querySelectorAll("[aria-invalid]").forEach((i) => i.removeAttribute("aria-invalid"));
  }
  function fieldError(field, message) {
    const slot = el("form-application").querySelector(`[data-error-for="${field}"]`);
    if (!slot) return false;
    slot.textContent = message;
    const input = slot.parentElement.querySelector("input, textarea, select");
    if (input) input.setAttribute("aria-invalid", "true");
    return true;
  }
  function formError(message) {
    const box = el("application-form-error");
    box.textContent = message;
    box.classList.remove("hidden");
  }

  async function openForm(application) {
    const form = el("form-application");
    form.reset();
    clearFormErrors();
    el("application-edit-id").value = application ? application.id : "";
    el("application-category-other-wrap").classList.add("hidden");
    el("application-form-title").textContent = application ? `Edit ${application.name}` : "Add Application";
    setButtonLabel(el("application-submit-btn"), application ? "check" : "plus", application ? "Save changes" : "Create application");
    form.classList.remove("hidden");
    // Category choices come from the Application Category master (active values).
    if (typeof loadMasterDropdowns === "function") await loadMasterDropdowns();
    if (application) {
      el("application-name").value = application.name;
      el("application-code").value = application.code;
      el("application-url").value = application.url || "";
      el("application-description").value = application.description || "";
      el("application-status").value = application.is_active ? "active" : "inactive";
      setSelectOrOther(el("application-category-select"), el("application-category-other-wrap"), el("application-category-other"), application.category || "");
    }
    form.scrollIntoView({ behavior: "smooth", block: "nearest" });
    el("application-name").focus();
  }
  function closeForm() {
    el("form-application").classList.add("hidden");
    el("form-application").reset();
    clearFormErrors();
  }

  function showServerErrors(result) {
    const data = result.data || {};
    let shown = false;
    if (Array.isArray(data.details)) {
      for (const detail of data.details) {
        const field = [...(detail.loc || [])].reverse().find((p) => typeof p === "string" && p !== "body");
        const message = String(detail.msg || "").replace(/^Value error,\s*/i, "");
        if (field && fieldError(field, message)) shown = true;
      }
    }
    if (data.error_code === "APPLICATION_ALREADY_EXISTS") shown = fieldError("name", data.message) || shown;
    if (data.error_code === "APPLICATION_CODE_ALREADY_EXISTS") shown = fieldError("code", data.message) || shown;
    if (!shown) formError(data.message || "The application could not be saved.");
    else formError("Please correct the highlighted fields.");
  }

  async function submitForm(event) {
    event.preventDefault();
    clearFormErrors();
    const editId = el("application-edit-id").value;
    const name = el("application-name").value.trim();
    const code = el("application-code").value.trim();
    let invalid = false;
    if (!name) {
      fieldError("name", "Application name is required.");
      invalid = true;
    }
    if (!code) {
      fieldError("code", "Application code is required.");
      invalid = true;
    }
    if (invalid) {
      formError("Please correct the highlighted fields.");
      return;
    }
    const body = {
      name,
      code,
      description: el("application-description").value.trim() || null,
      category: getSelectOrOther(el("application-category-select"), el("application-category-other")) || null,
      url: el("application-url").value.trim() || null,
      is_active: el("application-status").value === "active",
    };
    await withLoading(el("application-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
      const result = await safeApi(editId ? `/api/v1/applications/${editId}` : "/api/v1/applications", {
        method: editId ? "PUT" : "POST",
        body,
      });
      if (result.status === 200 || result.status === 201) {
        toast(editId ? "Application updated." : "Application created.", "ok");
        closeForm();
        await refreshEverywhere();
      } else {
        showServerErrors(result);
      }
    });
  }

  /* ---------------- activate / deactivate ---------------- */

  async function setActive(id, makeActive) {
    const a = findLoaded(id);
    if (!a) return;
    const held = a.employee_count || 0;
    const message = makeActive
      ? `Activate “${a.name}”? It can be given to employees again.`
      : `Deactivate “${a.name}”? It will no longer be given to anyone new and disappears from the Employee form.` +
        (held ? ` The ${held} employee${held === 1 ? "" : "s"} who already ${held === 1 ? "has" : "have"} it keep${held === 1 ? "s" : ""} it, marked inactive, until you revoke it.` : "");
    if (!(await confirmModal(message))) return;
    const result = await safeApi(makeActive ? `/api/v1/applications/${id}/reactivate` : `/api/v1/applications/${id}`, {
      method: makeActive ? "PATCH" : "DELETE",
    });
    if (result.status === 200) {
      toast(makeActive ? "Application activated." : "Application deactivated.", "ok");
      await refreshEverywhere();
    }
  }

  // The Employee form's checkbox list (applicationsCache in app.js) and this
  // table both come from the same master, so one change refreshes both.
  async function refreshEverywhere() {
    if (typeof loadApplications === "function") await loadApplications();
    else await load();
    loadCategories();
  }

  /* ---------------- view drawer ---------------- */

  function openView(id) {
    const a = findLoaded(id);
    if (!a) return;
    el("application-view-title").textContent = a.name;
    el("application-view-facts").innerHTML = [
      ["Application name", a.name],
      ["Application code", a.code],
      ["Category", a.category],
      ["Application URL", a.url],
      ["Description", a.description],
      ["Status", a.is_active ? "Active" : "Inactive"],
      ["Assigned employees", a.employee_count ?? 0],
      ["Created", a.created_at],
      ["Last updated", a.updated_at],
    ]
      .map(([label, value]) => `<dt>${esc(label)}</dt><dd>${value === null || value === undefined || value === "" ? "—" : esc(typeof value === "string" && /^\d{4}-\d\d-\d\dT/.test(value) ? fmt(value) : value)}</dd>`)
      .join("");
    el("application-view-access").classList.toggle("hidden", !canManageAccess());
    el("application-view-access").dataset.id = a.id;
    el("application-view-modal").classList.remove("hidden");
    el("application-view-close").focus();
  }
  function closeView() {
    el("application-view-modal").classList.add("hidden");
  }

  /* ---------------- access management drawer ---------------- */

  function accessSummary() {
    const s = am.access;
    const a = s.app;
    const total = s.data ? s.data.total : a.employee_count ?? 0;
    el("am-access-title").textContent = "Access management";
    el("am-access-summary").innerHTML = `
      <div class="am-summary-main"><strong>${esc(a.name)}</strong> ${mono(a.code)} ${statusPill(a.is_active)}</div>
      <div class="am-summary-meta">${total} employee${total === 1 ? "" : "s"} with access${a.category ? ` &middot; ${esc(a.category)}` : ""}</div>`;
    const note = el("am-access-note");
    note.classList.toggle("hidden", a.is_active);
    note.textContent = a.is_active
      ? ""
      : "This application is inactive. Existing access is kept and can be revoked, but no one new can be given it. Activate it to give access again.";
    el("am-grant").classList.toggle("hidden", !a.is_active);
  }

  async function openAccess(id) {
    const a = findLoaded(id) || (await fetchApplication(id));
    if (!a) return;
    closeView();
    am.access = { app: a, q: "", page: 1, size: 10, data: null, seq: 0, picks: new Map(), grantQ: "", grantSeq: 0, changed: false, timer: null, grantTimer: null, opener: document.activeElement };
    el("am-access-search").value = "";
    el("am-grant-search").value = "";
    accessSummary();
    el("application-access-modal").classList.remove("hidden");
    el("am-access-close").focus();
    loadAccess();
    if (a.is_active) loadCandidates();
    renderPicks();
  }
  async function fetchApplication(id) {
    const result = await safeApi(`/api/v1/applications/${id}`);
    return result.status === 200 ? result.data.data : null;
  }
  async function closeAccess() {
    const s = am.access;
    el("application-access-modal").classList.add("hidden");
    am.access = null;
    if (s && s.changed) {
      load();
      if (typeof loadEmployees === "function") loadEmployees();
    }
    if (s && s.opener && document.contains(s.opener)) s.opener.focus();
  }

  function accessRowHtml(row) {
    return `<tr>
      <td><strong>${esc(row.full_name)}</strong><div class="am-sub">${esc(row.email)}</div></td>
      <td>${row.employee_code ? mono(row.employee_code) : dash}</td>
      <td><span class="status-pill">${esc(row.status)}</span></td>
      <td>${row.granted_at ? `${esc(fmt(row.granted_at))}${row.granted_by ? `<div class="am-sub">by ${esc(row.granted_by)}</div>` : ""}` : NO_DATE}</td>
      <td class="am-actions"><button type="button" class="danger" data-am-revoke="${row.employee_id}" aria-label="Revoke access for ${esc(row.full_name)}">${icon("revoke")}Revoke</button></td>
    </tr>`;
  }

  async function loadAccess() {
    const s = am.access;
    if (!s) return;
    const listEl = el("am-access-list");
    const pagerEl = el("am-access-pager");
    const mySeq = ++s.seq;
    listEl.setAttribute("aria-busy", "true");
    listEl.innerHTML = skeletonTable(3);
    const params = new URLSearchParams({ limit: String(s.size), offset: String((s.page - 1) * s.size) });
    if (s.q.trim()) params.set("search", s.q.trim());
    const result = await safeApi(`/api/v1/applications/${s.app.id}/access?${params}`);
    if (am.access !== s || mySeq !== s.seq) return;
    listEl.setAttribute("aria-busy", "false");
    if (result.status !== 200) {
      pagerEl.innerHTML = "";
      listEl.innerHTML = errorState(result.data.message || "The list could not be loaded.", "access-retry", "Retry");
      return;
    }
    const data = result.data.data;
    if (data.total > 0 && !data.items.length && s.page > 1) {
      s.page = Math.max(1, Math.ceil(data.total / s.size));
      return loadAccess();
    }
    s.data = data;
    if (!s.q.trim()) s.app.employee_count = data.total;
    accessSummary();
    if (!data.items.length) {
      listEl.innerHTML = emptyState(s.q.trim() ? "No one with access matches this search." : "No employees have access to this application yet.");
      pagerEl.innerHTML = "";
      return;
    }
    listEl.innerHTML = `<table class="am-table am-access-table"><thead><tr>
      <th scope="col">Employee</th><th scope="col">Employee ID</th><th scope="col">Status</th><th scope="col">Access since</th><th scope="col">Actions</th>
    </tr></thead><tbody>${data.items.map(accessRowHtml).join("")}</tbody></table>`;
    pagerEl.innerHTML = pagerHtml(data, s.size, s.page, "amacc");
  }

  async function revoke(employeeId) {
    const s = am.access;
    if (!s) return;
    const row = ((s.data && s.data.items) || []).find((r) => String(r.employee_id) === String(employeeId));
    const who = row ? row.full_name : `employee #${employeeId}`;
    if (!(await confirmModal(`Revoke ${who}'s access to “${s.app.name}”? They will no longer be listed as having it. The change is recorded in the audit log.`))) return;
    const result = await safeApi(`/api/v1/applications/${s.app.id}/access/${employeeId}`, { method: "DELETE" });
    if (result.status === 200) {
      toast("Access revoked.", "ok");
      s.changed = true;
      await loadAccess();
      if (s.app.is_active) loadCandidates();
    }
  }

  /* give access */

  function renderPicks() {
    const s = am.access;
    if (!s) return;
    const n = s.picks.size;
    el("am-grant-count").textContent = n ? `${n} selected` : "No one selected";
    el("am-grant-btn").disabled = n === 0;
  }

  async function loadCandidates() {
    const s = am.access;
    if (!s) return;
    const box = el("am-grant-results");
    const mySeq = ++s.grantSeq;
    box.setAttribute("aria-busy", "true");
    const params = new URLSearchParams({ limit: "20" });
    if (s.grantQ.trim()) params.set("search", s.grantQ.trim());
    const result = await safeApi(`/api/v1/applications/${s.app.id}/access/candidates?${params}`);
    if (am.access !== s || mySeq !== s.grantSeq) return;
    box.setAttribute("aria-busy", "false");
    if (result.status !== 200) {
      box.innerHTML = errorState(result.data.message || "Employees could not be loaded.", "grant-retry", "Retry");
      return;
    }
    const rows = result.data.data || [];
    // anything ticked earlier stays ticked (and listed) while the search changes
    const shown = new Set(rows.map((r) => r.employee_id));
    const carried = [...s.picks.values()].filter((p) => !shown.has(p.employee_id));
    const all = [...carried, ...rows];
    if (!all.length) {
      box.innerHTML = `<p class="am-empty">${s.grantQ.trim() ? "No matching employees without this access." : "Everyone eligible already has this application."}</p>`;
      return;
    }
    box.innerHTML = all
      .map(
        (r) => `<label class="am-pick">
        <input type="checkbox" value="${r.employee_id}" ${s.picks.has(r.employee_id) ? "checked" : ""} />
        <span class="am-pick-text"><strong>${esc(r.full_name)}</strong><span class="am-sub">${esc(r.email)}${r.employee_code ? ` &middot; ${esc(r.employee_code)}` : ""}</span></span>
      </label>`
      )
      .join("");
    box.querySelectorAll('input[type="checkbox"]').forEach((box2) => {
      const row = all.find((r) => String(r.employee_id) === box2.value);
      box2.onchange = () => {
        if (box2.checked) s.picks.set(row.employee_id, row);
        else s.picks.delete(row.employee_id);
        renderPicks();
      };
    });
  }

  async function grant() {
    const s = am.access;
    if (!s || !s.picks.size) return;
    const ids = [...s.picks.keys()];
    await withLoading(el("am-grant-btn"), "Giving access…", async () => {
      const result = await safeApi(`/api/v1/applications/${s.app.id}/access`, { method: "POST", body: { employee_ids: ids } });
      if (result.status === 201 || result.status === 200) {
        const { granted, already_assigned: already } = result.data.data;
        toast(
          `Access given to ${granted.length} employee${granted.length === 1 ? "" : "s"}` + (already.length ? ` (${already.length} already had it).` : "."),
          "ok"
        );
        s.picks.clear();
        s.changed = true;
        renderPicks();
        await loadAccess();
        loadCandidates();
      }
    });
    renderPicks();
  }

  /* ---------------- employee details: applications section ---------------- */

  async function renderEmployeeApps(employee) {
    const box = el("employee-view-apps");
    if (!box) return;
    const token = (box.dataset.token = String(Date.now() + Math.random()));
    box.innerHTML = '<p class="am-empty">Loading applications…</p>';
    const result = await safeApi(`/api/v1/employees/${employee.id}/applications`);
    if (box.dataset.token !== token) return;
    if (result.status !== 200) {
      box.innerHTML = `<p class="am-empty">Applications could not be loaded.</p>`;
      return;
    }
    const rows = result.data.data || [];
    const manage = canManageAccess();
    const exited = employee.status === "exited";
    const list = rows.length
      ? `<ul class="am-emp-list">${rows
          .map(
            (r) => `<li class="am-emp-item${r.is_active ? "" : " am-row-inactive"}">
          <span class="am-emp-main"><strong>${esc(r.name)}</strong> ${mono(r.code)}${r.is_active ? "" : ' <span class="status-pill bad">Inactive</span>'}
            <span class="am-sub">${r.category ? esc(r.category) + " &middot; " : ""}${r.granted_at ? "Since " + esc(fmt(r.granted_at)) : "Granted before access dates were recorded"}${r.is_active ? "" : " &middot; on hold while the application is inactive"}</span></span>
          ${manage ? `<button type="button" class="danger" data-emp-revoke="${r.application_id}" aria-label="Revoke ${esc(r.name)}">${icon("revoke")}Revoke</button>` : ""}
        </li>`
          )
          .join("")}</ul>`
      : '<p class="am-empty">No applications assigned.</p>';
    box.innerHTML = list + (manage && !exited ? '<div class="am-emp-add" id="am-emp-add"></div>' : "") + (manage && exited ? '<p class="am-empty">This employee has exited, so no new access can be given.</p>' : "");
    const redraw = () => renderEmployeeApps(employee);
    box.querySelectorAll("[data-emp-revoke]").forEach((button) => {
      button.onclick = async () => {
        const row = rows.find((r) => String(r.application_id) === button.dataset.empRevoke);
        if (!(await confirmModal(`Revoke ${employee.full_name || "this employee"}'s access to “${row ? row.name : "this application"}”? The change is recorded in the audit log.`))) return;
        const done = await safeApi(`/api/v1/applications/${button.dataset.empRevoke}/access/${employee.id}`, { method: "DELETE" });
        if (done.status === 200) {
          toast("Access revoked.", "ok");
          employeeAppsChanged();
          redraw();
        }
      };
    });
    if (manage && !exited) {
      const mine = new Set(rows.map((r) => r.application_id));
      const options = await safeApi("/api/v1/applications?limit=100&status=active");
      if (box.dataset.token !== token || options.status !== 200) return;
      const free = (options.data.data.items || []).filter((a) => !mine.has(a.id));
      const add = el("am-emp-add");
      if (!add) return;
      add.innerHTML = free.length
        ? `<label class="rp-sr" for="am-emp-select">Application to give</label>
           <select id="am-emp-select"><option value="">Select an application…</option>${free.map((a) => `<option value="${a.id}">${esc(a.name)} (${esc(a.code)})</option>`).join("")}</select>
           <button type="button" class="primary" id="am-emp-grant" disabled>${icon("plus")}Give access</button>`
        : '<p class="am-empty">No other active applications to give.</p>';
      const select = el("am-emp-select");
      if (select) {
        select.onchange = () => (el("am-emp-grant").disabled = !select.value);
        el("am-emp-grant").onclick = async () => {
          const done = await safeApi(`/api/v1/applications/${select.value}/access`, { method: "POST", body: { employee_ids: [employee.id] } });
          if (done.status === 201 || done.status === 200) {
            toast("Access given.", "ok");
            employeeAppsChanged();
            redraw();
          }
        };
      }
    }
  }
  // The Employees table (Access-to dropdown) and the Application list carry
  // counts from before the change; refresh them quietly.
  function employeeAppsChanged() {
    if (typeof loadEmployees === "function") loadEmployees();
    load();
  }

  /* ---------------- wiring ---------------- */

  function wire() {
    if (am.wired || !el("applications-table")) return;
    am.wired = true;

    el("btn-new-application").onclick = () => openForm(null);
    el("application-cancel-btn").onclick = closeForm;
    el("form-application").onsubmit = submitForm;
    el("application-category-select").onchange = () => {
      el("application-category-other-wrap").classList.toggle("hidden", el("application-category-select").value !== "__other__");
    };
    el("application-code").addEventListener("blur", () => {
      const input = el("application-code");
      input.value = input.value.trim().replace(/\s+/g, "_").toUpperCase();
    });

    el("applications-search").addEventListener("input", () => {
      am.q = el("applications-search").value;
      clearTimeout(am.timer);
      am.timer = setTimeout(() => {
        am.page = 1;
        load();
      }, SEARCH_DEBOUNCE_MS);
    });
    el("applications-status-filter").onchange = () => {
      am.status = el("applications-status-filter").value;
      am.page = 1;
      load();
    };
    el("applications-category-filter").onchange = () => {
      am.category = el("applications-category-filter").value;
      am.page = 1;
      load();
    };

    const panel = el("mm-panel-application");
    panel.addEventListener("click", (event) => {
      const button = event.target.closest("[data-am-action],[data-am-page]");
      if (!button) return;
      const id = button.dataset.id;
      switch (button.dataset.amAction || `page-${button.dataset.amPage}`) {
        case "view": return openView(id);
        case "edit": { const a = findLoaded(id); if (a) openForm(a); return; }
        case "access": return openAccess(id);
        case "deactivate": return setActive(id, false);
        case "activate": return setActive(id, true);
        case "retry": return load();
        case "reset":
          am.q = ""; am.status = "all"; am.category = ""; am.page = 1;
          el("applications-search").value = "";
          el("applications-status-filter").value = "all";
          el("applications-category-filter").value = "";
          return load();
        case "page-prev": am.page = Math.max(1, am.page - 1); return load();
        case "page-next": am.page += 1; return load();
      }
    });
    panel.addEventListener("change", (event) => {
      if (event.target.matches("[data-am-size]")) {
        am.size = Number(event.target.value) || 25;
        am.page = 1;
        load();
      }
    });
    el("btn-export-applications").onclick = exportCsv;

    el("application-view-close").onclick = closeView;
    el("application-view-modal").onclick = (event) => event.target === el("application-view-modal") && closeView();
    el("application-view-access").onclick = () => openAccess(el("application-view-access").dataset.id);

    const modal = el("application-access-modal");
    el("am-access-close").onclick = closeAccess;
    modal.onclick = (event) => event.target === modal && closeAccess();
    el("am-access-search").addEventListener("input", () => {
      const s = am.access;
      if (!s) return;
      s.q = el("am-access-search").value;
      clearTimeout(s.timer);
      s.timer = setTimeout(() => { s.page = 1; loadAccess(); }, SEARCH_DEBOUNCE_MS);
    });
    el("am-grant-search").addEventListener("input", () => {
      const s = am.access;
      if (!s) return;
      s.grantQ = el("am-grant-search").value;
      clearTimeout(s.grantTimer);
      s.grantTimer = setTimeout(loadCandidates, SEARCH_DEBOUNCE_MS);
    });
    el("am-grant-btn").onclick = grant;
    modal.addEventListener("click", (event) => {
      const revokeBtn = event.target.closest("[data-am-revoke]");
      if (revokeBtn) return revoke(revokeBtn.dataset.amRevoke);
      const pageBtn = event.target.closest("[data-amacc-page]");
      if (pageBtn && am.access) {
        am.access.page = pageBtn.dataset.amaccPage === "next" ? am.access.page + 1 : Math.max(1, am.access.page - 1);
        return loadAccess();
      }
      const action = event.target.closest("[data-am-action]");
      if (action && action.dataset.amAction === "access-retry") return loadAccess();
      if (action && action.dataset.amAction === "grant-retry") return loadCandidates();
    });
    modal.addEventListener("change", (event) => {
      if (event.target.matches("[data-amacc-size]") && am.access) {
        am.access.size = Number(event.target.value) || 10;
        am.access.page = 1;
        loadAccess();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const confirmOpen = !el("confirm-modal").classList.contains("hidden");
      if (confirmOpen) return; // the confirm dialog handles its own Escape
      if (!el("application-access-modal").classList.contains("hidden")) closeAccess();
      else if (!el("application-view-modal").classList.contains("hidden")) closeView();
    });

    // Show fresh numbers whenever the Application master is opened.
    new MutationObserver(() => {
      if (!panel.classList.contains("hidden")) {
        load();
        loadCategories();
      }
    }).observe(panel, { attributes: true, attributeFilter: ["class"] });
  }

  async function exportCsv() {
    const rows = [];
    let offset = 0;
    for (;;) {
      const params = new URLSearchParams({ limit: "100", offset: String(offset), status: am.status });
      if (am.q.trim()) params.set("search", am.q.trim());
      if (am.category) params.set("category", am.category);
      const result = await safeApi(`/api/v1/applications?${params}`);
      if (result.status !== 200) return;
      const data = result.data.data;
      rows.push(...data.items);
      if (!data.has_more) break;
      offset += 100;
    }
    if (!rows.length) {
      toast("Nothing to export — no rows match the current view.", "bad");
      return;
    }
    const csv = toCsv(
      ["name", "code", "category", "url", "description", "status", "assigned_employees", "updated_at"],
      rows.map((a) => [a.name, a.code, a.category || "", a.url || "", a.description || "", a.is_active ? "Active" : "Inactive", a.employee_count ?? 0, a.updated_at || ""])
    );
    downloadCsv(`applications-${new Date().toISOString().slice(0, 10)}.csv`, csv);
    toast(`Exported ${rows.length} row${rows.length === 1 ? "" : "s"}.`, "ok");
  }

  window.NexusApplications = {
    // called by app.js whenever it (re)loads applications for the Employee form
    reload() {
      wire();
      load();
      loadCategories();
    },
    renderEmployeeApps,
  };
  wire();
})();
