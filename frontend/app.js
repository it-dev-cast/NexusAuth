const state = {
  accessToken: null,
  refreshToken: null,
  user: null,
};

const $ = (id) => document.getElementById(id);

// This page's own mount prefix — "" when served directly at its own
// root/port (e.g. :8300/ui), "/auth" when reverse-proxied under nginx's
// /auth/ location. Read from this very <script> tag's own (already
// correctly rewritten) src, via document.currentScript rather than a
// src*="..." selector — a selector literal containing "/static/" is itself
// rewritten by nginx's sub_filter (which rewrites every occurrence of that
// text in this file, not just real asset URLs), which previously broke
// this exact detection by making the comparison string drift in lockstep
// with the thing it was trying to detect. The marker below is built with
// .join("/") (not the literal string "/static/app.js") for the same
// reason — so it can't itself be rewritten into never matching.
const BASE_PATH = (() => {
  const script = document.currentScript;
  if (!script) return "";
  const marker = ["", "static", "app.js"].join("/");
  const path = new URL(script.src, window.location.href).pathname;
  const i = path.indexOf(marker);
  return i > 0 ? path.slice(0, i) : "";
})();
function withBasePath(path) {
  return path ? `${BASE_PATH}${path}` : path;
}

// Declared up here (not down with the rest of the reload-and-restore
// code below) specifically so the curtain check right after it can use
// the real constant instead of a second, driftable copy of the literal.
const SESSION_STORAGE_KEY = "nexusone.session";

// #restore-curtain (index.html) is visible by default via plain CSS —
// no script runs before this one to decide that, since this app's CSP
// blocks inline <script>. The very first thing this (external, so
// CSP-compliant) script does is resolve the one case it can answer
// immediately: no persisted session at all means there's nothing to
// restore, so reveal the real login page right away instead of waiting
// on the rest of the script to get around to it further down. The
// "there IS a session, still confirming it" case stays curtained until
// showGate()/showApp() run at the end of restoreSession() below.
if (!sessionStorage.getItem(SESSION_STORAGE_KEY)) {
  const curtain = $("restore-curtain");
  if (curtain) curtain.classList.add("hidden");
}

/* ============ Route (URL hash) <-> section ============
 * Each sidebar section now has its own real URL — /ui#employees,
 * /ui#companies, etc. — instead of every section living silently under
 * the bare /ui URL with no way to tell them apart from the address bar.
 * That's what makes "reload but stay on the same page" actually work:
 * the browser's address bar already carries the current page across a
 * real reload for free — no JS-side bookkeeping needed to remember which
 * section was open.
 */
const HASH_TO_SECTION = {
  "": "section-overview",
  overview: "section-overview",
  users: "section-users",
  companies: "section-companies",
  employees: "section-employees",
  departments: "section-departments",
  "job-roles": "section-job-roles",
  applications: "section-applications",
  suppliers: "section-suppliers",
  assets: "section-assets",
  manufacturers: "section-manufacturers",
  models: "section-asset-models",
  audit: "section-audit",
  events: "section-events",
  sessions: "section-sessions",
};
const SECTION_TO_HASH = Object.fromEntries(
  Object.entries(HASH_TO_SECTION)
    .filter(([hash]) => hash !== "" && hash !== "overview")
    .map(([hash, sectionId]) => [sectionId, hash])
);
SECTION_TO_HASH["section-overview"] = "overview";

function currentHashSection() {
  return HASH_TO_SECTION[location.hash.replace(/^#/, "")] || "section-overview";
}

/* ============ Reload-and-restore ============
 * Tokens live only in `state` (in-memory) — a plain page reload would
 * normally drop them and bounce back to the login gate. sessionStorage
 * (cleared when the tab closes, unlike localStorage) lets a reload —
 * including the ones fired after every create/update/delete below —
 * restore the same signed-in session; the URL hash above (which survives
 * a reload on its own) takes care of restoring the page itself.
 * (SESSION_STORAGE_KEY itself is declared near the top of the file,
 * above the curtain check that needs it before this point.)
 */
const PAGE_STATE_KEY = "nexusone.pageState";

function persistSession() {
  if (!state.accessToken) return;
  sessionStorage.setItem(
    SESSION_STORAGE_KEY,
    JSON.stringify({ accessToken: state.accessToken, refreshToken: state.refreshToken })
  );
}
function clearPersistedSession() {
  sessionStorage.removeItem(SESSION_STORAGE_KEY);
}
// Beyond which section was open, a handful of controls change what a
// section actually shows (the Employees company filter, status filters,
// each page's own search box) — without saving these too, a reload would
// land back on the right page but with the wrong company/filter/search
// applied, which reads just as much like "lost my place" as landing on
// the wrong page does.
function persistPageState() {
  sessionStorage.setItem(
    PAGE_STATE_KEY,
    JSON.stringify({
      employeeCompanyFilter: $("employee-company-filter").value,
      employeeIncludeExited: $("employee-include-exited").checked,
      supplierStatusFilter: $("supplier-status-filter").value,
      assetStatusFilter: $("asset-status-filter").value,
      usersSearch: $("users-search").value,
      companiesSearch: $("companies-search").value,
      employeesSearch: $("employees-search").value,
      suppliersSearch: $("suppliers-search").value,
      assetsSearch: $("assets-search").value,
      sessionsSearch: $("sessions-search").value,
      departmentsSearch: $("departments-search").value,
      jobRolesSearch: $("job-roles-search").value,
      applicationsSearch: $("applications-search").value,
      manufacturersSearch: $("manufacturers-search").value,
      assetModelsSearch: $("asset-models-search").value,
      departmentsIncludeInactive: $("departments-include-inactive").checked,
      jobRolesIncludeInactive: $("job-roles-include-inactive").checked,
      applicationsIncludeInactive: $("applications-include-inactive").checked,
      manufacturersIncludeInactive: $("manufacturers-include-inactive").checked,
      assetModelsIncludeInactive: $("asset-models-include-inactive").checked,
      departmentsParentFilter: $("departments-parent-filter").value,
      employeeDepartmentFilter: $("employee-department-filter").value,
      companiesSort: $("companies-sort").value,
      companiesTypeFilter: $("companies-type-filter").value,
    })
  );
}
function readPageState() {
  try {
    return JSON.parse(sessionStorage.getItem(PAGE_STATE_KEY)) || {};
  } catch {
    return {};
  }
}
// Persist the session and this page's filters/search, then do a real
// full page reload — used after every mutating action below so every
// piece of the page (not just one list) gets re-initialized from fresh
// backend data, while the URL hash already pins it to reopen on the
// exact same page.
function reloadPage() {
  persistSession();
  persistPageState();
  location.reload();
}

/* ============ NEXUS One theme system ============
 * Plain-JS equivalent of docs/ui/THEME_IMPLEMENTATION_GUIDE.md's
 * ThemeContext.tsx: one THEMES registry (so the picker never hardcodes a
 * second list), persistence under the same localStorage key the docs
 * specify, and System mode resolving to casterly-light/graphite-dark by
 * OS preference. Applied to <html> (data-theme + .dark), so both the
 * public landing page and the signed-in dashboard react to the same
 * chosen theme — see the matching :root[data-theme="..."] blocks in
 * styles.css. Brand chrome (the navy pixel-matched to the real logo,
 * frontend/branding/*.png) is deliberately never part of any theme
 * override, so it stays exactly as-is regardless of which theme is
 * selected.
 */
const THEME_STORAGE_KEY = "nexusone.theme";
// `swatch` is each theme's own --accent value (styles.css) copied here as
// a literal — the swatch dot needs a real color the instant the picker
// renders, before/regardless of that theme actually being applied, so it
// can't just read the live CSS variable (which reflects whatever theme is
// currently active, not each option's own).
const THEMES = [
  { id: "casterly-light", label: "Casterly Light", dark: false, swatch: "#678b27" },
  { id: "executive-white", label: "Executive White", dark: false, swatch: "#3f3f46" },
  { id: "ocean-blue", label: "Ocean Blue", dark: false, swatch: "#1d4ed8" },
  { id: "slate-professional", label: "Slate Professional", dark: false, swatch: "#475569" },
  { id: "emerald", label: "Emerald", dark: false, swatch: "#059669" },
  { id: "purple-enterprise", label: "Purple Enterprise", dark: false, swatch: "#6d28d9" },
  { id: "casterly-erp-green", label: "Casterly ERP Green", dark: false, swatch: "#2f7d4f" },
  { id: "graphite-dark", label: "Graphite Dark", dark: true, swatch: "#818cf8" },
  { id: "midnight-blue", label: "Midnight Blue", dark: true, swatch: "#6366f1" },
];

function systemDefaultTheme() {
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "graphite-dark" : "casterly-light";
}

function applyTheme(themeId) {
  const theme = THEMES.find((t) => t.id === themeId) || THEMES[0];
  document.documentElement.dataset.theme = theme.id;
  document.documentElement.classList.toggle("dark", theme.dark);
  // The trigger is icon-only now (no dot/label on it) — the panel is the
  // only place a theme's swatch/name/checkmark shows. Re-render it so the
  // active row's highlight follows; cheap (9 rows) and only actually runs
  // while the panel exists in the DOM.
  if ($("theme-swatch-panel")) renderThemeSwatchPanel(theme.id);
}

function renderThemeSwatchPanel(activeId) {
  // The trigger itself is icon-only (no "Theme" label next to it) — this
  // heading is the only place that word still shows, right above the
  // options once the panel is actually open.
  const heading = `<p class="theme-swatch-panel-heading">Theme</p>`;
  const options = THEMES.map(
    (t) => `<button type="button" class="theme-swatch-option${t.id === activeId ? " active" : ""}" data-theme-option="${t.id}">
      <span class="theme-swatch-dot" style="background:${t.swatch}"></span>
      ${t.label}
      ${
        t.id === activeId
          ? `<svg class="theme-swatch-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
          : ""
      }
    </button>`
  ).join("");
  $("theme-swatch-panel").innerHTML = heading + options;
  $("theme-swatch-panel").querySelectorAll("[data-theme-option]").forEach((btn) => {
    btn.onclick = () => {
      const themeId = btn.getAttribute("data-theme-option");
      localStorage.setItem(THEME_STORAGE_KEY, themeId);
      applyTheme(themeId);
      $("theme-swatch-panel").classList.add("hidden");
    };
  });
}

function initThemeSystem() {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  applyTheme(stored || systemDefaultTheme());

  $("theme-swatch-trigger").onclick = (event) => {
    event.preventDefault();
    $("theme-swatch-panel").classList.toggle("hidden");
  };
  document.addEventListener("click", (event) => {
    const dropdown = $("theme-swatch-trigger").closest(".theme-swatch-dropdown");
    if (dropdown && !dropdown.contains(event.target)) {
      $("theme-swatch-panel").classList.add("hidden");
    }
  });
}
initThemeSystem();

/* ============ Sidebar collapse (icons-only) ============
 * Persisted the same way as the theme choice (localStorage, not the
 * per-tab sessionStorage used for page/search state above) so the
 * user's chosen density survives a reload or reopening the app, not
 * just navigation within the current tab.
 */
const SIDEBAR_COLLAPSE_KEY = "nexusone.sidebar.collapsed";

function applySidebarCollapsed(collapsed) {
  const sidebar = document.querySelector(".sidebar");
  const btn = $("btn-sidebar-collapse");
  if (!sidebar) return;
  sidebar.classList.toggle("collapsed", collapsed);
  if (btn) {
    const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
    btn.title = label;
    btn.setAttribute("aria-label", label);
  }
}

function initSidebarCollapse() {
  // Icon-only mode drops each item's visible <span> label, so give every
  // nav item a hover tooltip built from that same label instead of
  // hardcoding a second copy of the nav list.
  document.querySelectorAll(".nav-item").forEach((item) => {
    if (!item.title) {
      const label = item.querySelector("span");
      if (label) item.title = label.textContent.trim();
    }
  });

  applySidebarCollapsed(localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === "1");

  const btn = $("btn-sidebar-collapse");
  if (btn) {
    btn.onclick = () => {
      const next = !document.querySelector(".sidebar").classList.contains("collapsed");
      localStorage.setItem(SIDEBAR_COLLAPSE_KEY, next ? "1" : "0");
      applySidebarCollapsed(next);
    };
  }
}
initSidebarCollapse();

// Shared icon set for action buttons across the app, matching the sidebar's
// existing SVG style (viewBox 0 0 24 24, stroke-based, currentColor). One
// icon per action verb, reused everywhere that verb appears rather than each
// call site inventing its own — see .btn-icon in styles.css for sizing.
const ICONS = {
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  delete: '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
  deactivate: '<circle cx="12" cy="12" r="9"/><line x1="6" y1="6" x2="18" y2="18"/>',
  reactivate: '<path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 3 21 9 15 9"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  view: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/>',
  access: '<circle cx="7" cy="15" r="4"/><path d="M9.5 12.5 20 2"/><path d="m17.5 4.5 2 2"/><path d="m14.5 7.5 2 2"/>',
  // Filled dots (each overrides the shared <svg>'s fill="none" itself) —
  // a stroked circle at this radius would just render as a blob, not a
  // clean dot. Vertical layout ("⋮") — see .row-actions button.icon-btn.
  more: '<circle cx="12" cy="5" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="19" r="1.6" fill="currentColor" stroke="none"/>',
  close: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  login: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/>',
  register: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/>',
  link: '<path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" y1="12" x2="16" y2="12"/>',
  unlock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  revoke: '<circle cx="12" cy="12" r="9"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
  // Used on the read-only ".facts" rows (Current user / JWT claims /
  // Department detail) — one icon per field, not per action — via
  // fact()/facts() below rather than icon()/.btn-icon.
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.5-7 8-7s8 3 8 7"/>',
  users: '<circle cx="9" cy="7" r="3"/><path d="M2 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2"/><circle cx="17" cy="8" r="2.2"/><path d="M21 21v-1.6a4 4 0 0 0-3-3.87"/>',
  shield: '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/>',
  building: '<path d="M4 21V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v16"/><path d="M14 21v-9a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v9"/><path d="M2 21h20"/>',
  clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/>',
  hash: '<line x1="9" y1="3" x2="7" y2="21"/><line x1="17" y1="3" x2="15" y2="21"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/>',
  activity: '<polyline points="3 12 8 12 10 6 14 18 16 12 21 12"/>',
  note: '<path d="M8 3h8a1 1 0 0 1 1 1v16l-5-3-5 3V4a1 1 0 0 1 1-1z"/><line x1="9.5" y1="8" x2="14.5" y2="8"/><line x1="9.5" y1="11" x2="14.5" y2="11"/>',
  // Same set again, this time for the entity-form field labels (Companies/
  // Employees/Departments/Job Roles/Applications/Suppliers/Assets — see
  // .field-icon in styles.css). Those labels are static markup in
  // index.html, not JS-rendered, so the <svg> there is a literal copy of
  // this path data rather than a call through icon()/factIcon() — kept
  // here too so every icon in the app has exactly one definition to update.
  tag: '<path d="M20.59 13.41 11 3.83A2 2 0 0 0 9.59 3.24L4 3a1 1 0 0 0-1 1l.24 5.59a2 2 0 0 0 .59 1.41l9.58 9.58a2 2 0 0 0 2.83 0l4.35-4.35a2 2 0 0 0 0-2.82Z"/><circle cx="7.5" cy="7.5" r="1"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  mappin: '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
  briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
  departments: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  factory: '<rect x="3" y="10" width="18" height="11" rx="1"/><path d="M7 10V6l4 3V6l4 3"/><line x1="17" y1="6" x2="17" y2="3"/>',
  barcode: '<line x1="4" y1="4" x2="4" y2="20"/><line x1="8" y1="4" x2="8" y2="20"/><line x1="11" y1="4" x2="11" y2="20"/><line x1="15" y1="4" x2="15" y2="20"/><line x1="18" y1="4" x2="18" y2="20"/><line x1="21" y1="4" x2="21" y2="20"/>',
};
function icon(name) {
  const body = ICONS[name];
  if (!body) return "";
  return `<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

// Same icon set, sized/colored for a .facts <dt> label instead of a button
// (see .fact-icon in styles.css) — used by facts() below.
function factIcon(name) {
  const body = ICONS[name];
  if (!body) return "";
  return `<svg class="fact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

// Every real date this app ever formats comes from the backend as an ISO
// 8601 timestamp (e.g. "2026-09-08T11:49:30.021036+05:30") — anchoring on
// that shape instead of a bare "is this string long enough?" check. The
// old length-only heuristic (`length > 8`) let JS's notoriously loose
// Date parser misfire on ordinary text that happens to be long and
// contain a 4-digit number — e.g. "Dell Latitude 5420" parsed as
// "Jan 1, 5420" (the parser read "5420" as a year and ignored the rest),
// silently corrupting a plain manufacturer/model string into a garbage
// date the moment something used fmt() to display it (see Asset detail's
// Digital Twin facts).
const ISO_DATE_SHAPE = /^\d{4}-\d{2}-\d{2}/;

function fmt(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    const date = new Date(value * 1000);
    if (!Number.isNaN(date.getTime()) && value > 1000000000) return date.toLocaleString();
    return String(value);
  }
  if (ISO_DATE_SHAPE.test(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) return date.toLocaleString();
  }
  if (Array.isArray(value)) return value.join(", ") || "—";
  return String(value);
}

function toast(message, kind = "") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast ${kind}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), 3200);
}

// On-screen confirmation dialog for destructive actions (revoke session,
// deactivate company, delete employee, dispose asset) — an in-app modal
// styled like the rest of the app, instead of the browser's native
// confirm() popup. Returns a Promise<boolean>: true only if the user
// clicked Confirm; clicking Cancel, clicking the backdrop, or pressing
// Escape all resolve false, same as dismissing a native confirm().
function confirmModal(message) {
  const overlay = $("confirm-modal");
  const confirmBtn = $("confirm-modal-confirm");
  const cancelBtn = $("confirm-modal-cancel");
  $("confirm-modal-message").textContent = message;
  overlay.classList.remove("hidden");

  return new Promise((resolve) => {
    const finish = (result) => {
      overlay.classList.add("hidden");
      confirmBtn.onclick = null;
      cancelBtn.onclick = null;
      overlay.onclick = null;
      document.removeEventListener("keydown", onKeydown);
      resolve(result);
    };
    const onKeydown = (e) => {
      if (e.key === "Escape") finish(false);
    };
    confirmBtn.onclick = () => finish(true);
    cancelBtn.onclick = () => finish(false);
    overlay.onclick = (e) => {
      if (e.target === overlay) finish(false);
    };
    document.addEventListener("keydown", onKeydown);
    confirmBtn.focus();
  });
}

// Thin top-of-page progress bar for the window between a reload starting
// and the restored session/data actually being ready — without this the
// page just sits on an empty "Total 0 / Showing 0" shell with no
// indication anything is happening.
function showPageLoading() {
  const bar = $("page-loading-bar");
  bar.classList.remove("hidden", "done");
  void bar.offsetWidth; // force reflow so the width transition below actually animates from 0
  bar.classList.add("active");
}
function hidePageLoading() {
  const bar = $("page-loading-bar");
  bar.classList.remove("active");
  bar.classList.add("done");
  setTimeout(() => bar.classList.add("hidden"), 500);
}

function facts(target, rows) {
  $(target).innerHTML = rows
    .map(([label, value, iconName]) => `<dt>${factIcon(iconName)}${label}</dt><dd>${fmt(value)}</dd>`)
    .join("");
}

function table(headers, rows, empty) {
  // A richer "nothing here" state than a bare line of muted text — every
  // page's main data table (Users, Companies, Employees, ...) goes through
  // this one function, so this one change gives all of them the same
  // deliberate, designed empty state instead of it reading as a
  // half-loaded blank area.
  if (!rows) {
    return `<div class="empty-state">
      <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M3 7l3-4h12l3 4"/><path d="M3 12h5a2 2 0 0 0 4 0h5"/></svg>
      <p class="empty-state-text">${empty}</p>
    </div>`;
  }
  return `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
}

// Rendered into a page's table container the instant its loadX() function
// starts (before the request resolves), so switching sections — or a slow
// network — reads as "loading" instead of a blank flash between the old
// page's content disappearing and the new page's table() call landing.
// Every renderXTable() below overwrites the same container's innerHTML on
// success, and every error path replaces it with its own message, so this
// never lingers once the real load settles either way.
function skeletonTable(rowCount = 6) {
  return `<div class="skeleton-table">${'<div class="skeleton-row"></div>'.repeat(rowCount)}</div>`;
}

// docs/ui/COMPONENT_GUIDELINES.md §8: "Avoid exposing raw values such as
// qc_failed or awaiting_parts when the UI can show a business-friendly
// label." nexusAuth's raw values are its own snake_case status/action
// names (in_repair, read_only, role_change, ...) — humanize() is the
// generic version of that rule for this app: display-only, never touches
// the underlying value used in API calls/option values.
function humanize(value) {
  if (value === null || value === undefined || value === "") return value;
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

// docs/ui/COMPONENT_GUIDELINES.md §9: every async action needs a "local
// action loading" state, not just an eventual toast — otherwise a slow
// request invites a double-click (duplicate company/employee/etc.) with
// no feedback that the first click even registered. This is the plain-JS
// equivalent of the docs' Button `isLoading` prop: disable the button and
// swap its label for the duration of the async action, always restoring
// it (even on error) via finally.
async function withLoading(button, label, fn) {
  // innerHTML (not textContent) so a button carrying an icon (see icon() /
  // setButtonLabel() above) gets its icon back afterwards instead of being
  // left as bare text once the loading label below overwrites it.
  const originalHTML = button.innerHTML;
  button.disabled = true;
  button.textContent = label;
  try {
    return await fn();
  } finally {
    button.disabled = false;
    // Only restore the pre-loading label if nothing else changed it while
    // fn() ran. On success, resetCompanyForm()/resetEmployeeForm()/etc.
    // already set the submit button back to its correct next-use label
    // ("Create X" after a successful edit closes the form) — blindly
    // restoring `originalHTML` here would stomp that back to "Save changes".
    // On failure nothing else touches the button, so this still restores
    // it correctly.
    if (button.textContent === label) button.innerHTML = originalHTML;
  }
}

// Sets a button's label to an icon + text together, used anywhere a
// button's text swaps at runtime (Create X <-> Save changes, etc.) so the
// icon stays in sync with the label instead of a plain textContent
// assignment silently dropping it.
function setButtonLabel(button, iconName, text) {
  button.innerHTML = icon(iconName) + text;
}

// Shared CSV export, used by every list page's Export button (see
// wireCsvExport() below) — one escaping/download implementation instead
// of each page reinventing it. Per RFC 4180: a value gets wrapped in
// quotes (with any internal quote doubled) only if it actually contains
// a comma, quote, or newline, so a plain value like "Dell" stays
// unquoted and readable when opened straight in a spreadsheet.
function toCsv(headers, rows) {
  const escape = (value) => {
    const str = value === null || value === undefined ? "" : String(value);
    return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  };
  const lines = [headers.map(escape).join(","), ...rows.map((row) => row.map(escape).join(","))];
  // \r\n line endings — the CSV spec's own recommendation, and what keeps
  // Excel (as opposed to a plain text editor) from occasionally treating
  // the whole file as one line on some platforms.
  return lines.join("\r\n");
}

function downloadCsv(filename, csvText) {
  // "﻿" (a UTF-8 BOM) up front — without it, Excel guesses the file's
  // encoding from raw bytes alone and mis-renders anything outside plain
  // ASCII (e.g. the — and … characters already used throughout this UI,
  // should either ever end up in an exported name/value) as garbled
  // symbols instead of the actual character.
  const blob = new Blob(["﻿" + csvText], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// Wires one list page's Export button: pulls whatever's currently
// filtered into that page's own table (same filterItems(...) call the
// page's render function already uses, so the export always matches
// what's actually on screen — respecting the search box and any
// status/type/company filter already applied server-side into the
// cache), maps each item through rowMapper, and downloads it.
function wireCsvExport(buttonId, { headers, getFilteredItems, rowMapper, filenamePrefix }) {
  $(buttonId).onclick = () => {
    const items = getFilteredItems();
    if (!items.length) {
      toast("Nothing to export — no rows match the current view.", "bad");
      return;
    }
    const csv = toCsv(headers, items.map(rowMapper));
    const stamp = new Date().toISOString().slice(0, 10);
    downloadCsv(`${filenamePrefix}-${stamp}.csv`, csv);
    toast(`Exported ${items.length} row${items.length === 1 ? "" : "s"}.`, "ok");
  };
}

// Generic client-side search used on every list page's search box. Filters
// whatever page (up to 100 rows — the API's own pagination cap) is already
// loaded in memory; it does not call the backend, so it can't reach rows
// beyond what's currently fetched. Good enough for "find this one row on
// the page I'm looking at" without adding a server-side search endpoint.
function filterItems(items, query, fields) {
  if (!query) return items;
  const q = query.trim().toLowerCase();
  if (!q) return items;
  // Require every typed word to be found — not the whole typed phrase
  // inside one single field. Without this, typing "Dell A" for an asset
  // whose manufacturer is "Dell" and whose model is "A..." matched
  // nothing, even though both words are genuinely there — they just live
  // in two different columns, not one.
  //
  // Each term is matched from the LEFT edge of a WORD, not the left edge
  // of the whole field. Matching against the whole field only (a previous
  // version of this function) broke the most basic searches — "Doe" no
  // longer found "John Doe" (that's the field's second word, not its
  // start), and "casterly" no longer found "john@casterly.com" (same
  // issue: it's not where the email field itself starts). Splitting each
  // field into words and prefix-matching per word fixes both while still
  // rejecting a match buried in the MIDDLE of a single word — "ook" still
  // doesn't match "EliteBook", since that's not where the word "elitebook"
  // starts either. Split the query the same way the fields below are
  // split (on any non-alphanumeric character, not just whitespace) —
  // otherwise a query containing punctuation (an email, a tag like
  // "AST-xxx@casterly.com") stays one giant term that can never
  // prefix-match a word, since the fields' own words have already had
  // that punctuation stripped out.
  const terms = q.split(/[^a-z0-9]+/).filter(Boolean);
  return items.filter((item) => {
    const words = fields.flatMap((field) =>
      String(item[field] ?? "")
        .toLowerCase()
        .split(/[^a-z0-9]+/)
        .filter(Boolean)
    );
    return terms.every((term) => words.some((word) => word.startsWith(term)));
  });
}

// Search-suggestions dropdown — every page's search box already filters
// its table live on every keystroke (see each page's own
// `$("x-search").oninput`, wired independently of this), but that means
// scrolling the table to see what matched. This adds a small attached
// dropdown, right under the box, listing the first few matches by name as
// soon as a single character is typed — so a match can be spotted (and
// jumped to, by clicking it) without leaving the search box. Reuses the
// same filterItems() the table itself uses, so "what's suggested" and
// "what the table shows" never disagree.
const SEARCH_SUGGEST_LIMIT = 8;
function wireSearchSuggestions(inputId, panelId, getCache, fields, primaryFn, secondaryFn) {
  const input = $(inputId);
  const panel = $(panelId);
  const hide = () => panel.classList.add("hidden");
  const render = () => {
    const query = input.value.trim();
    if (!query) {
      hide();
      return;
    }
    const matches = filterItems(getCache(), query, fields).slice(0, SEARCH_SUGGEST_LIMIT);
    // Deliberately not fmt() here — fmt() guesses at dates/numbers for
    // table cells, and a plain label like an asset tag ("TAG-1178...")
    // can accidentally parse as a Date and render as a bogus timestamp
    // instead of the actual tag. A suggestion label is always just text.
    panel.innerHTML = matches.length
      ? matches
          .map((item, i) => {
            const primary = primaryFn(item);
            const secondary = secondaryFn && secondaryFn(item);
            return `<button type="button" class="search-suggest-option" data-suggest-index="${i}">
              <span class="search-suggest-primary">${primary === null || primary === undefined || primary === "" ? "—" : String(primary)}</span>
              ${secondary ? `<span class="search-suggest-secondary">${String(secondary)}</span>` : ""}
            </button>`;
          })
          .join("")
      : `<p class="search-suggest-empty">No matches</p>`;
    panel.querySelectorAll("[data-suggest-index]").forEach((btn) => {
      btn.onclick = () => {
        const item = matches[Number(btn.getAttribute("data-suggest-index"))];
        input.value = primaryFn(item);
        input.dispatchEvent(new Event("input")); // re-runs the page's own table filter with the completed term
        hide();
      };
    });
    panel.classList.remove("hidden");
  };
  input.addEventListener("input", render);
  input.addEventListener("focus", () => {
    if (input.value.trim()) render();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  document.addEventListener("click", (event) => {
    if (!panel.classList.contains("hidden") && event.target !== input && !panel.contains(event.target)) hide();
  });
}

// Searchable combobox over a plain <select> — for a <select> with a large
// option list (the Employees page's Company filter: 1000+ companies),
// typing a letter triggers the BROWSER's own typeahead, which jumps to
// *and immediately commits* the first matching option before the user has
// actually chosen one — typing "a" silently filters the page to whichever
// company happens to be first alphabetically, with no chance to keep
// narrowing or to back out. This wraps the <select> (kept exactly as
// before — hidden, but still the one thing every other .value/.onchange
// read/write in this file touches) with a visible text input: typing only
// filters a dropdown of matches, and nothing is actually selected — the
// underlying <select>'s value doesn't change, no change event fires —
// until a match is clicked or Enter is pressed on the highlighted one.
function wireSearchableSelect(selectId, inputId, panelId) {
  const select = $(selectId);
  const input = $(inputId);
  const panel = $(panelId);
  let highlighted = -1;

  function currentLabel() {
    const opt = select.options[select.selectedIndex];
    return opt ? opt.textContent : "";
  }
  // Called after this file sets select.value programmatically elsewhere
  // (loading the option list, restoring saved page state, a "view this
  // department's people" drill-down) — the visible input has no way to
  // know that happened on its own.
  function refresh() {
    input.value = currentLabel();
  }
  function hide() {
    panel.classList.add("hidden");
    highlighted = -1;
  }
  function commit(option) {
    select.value = option.value;
    select.dispatchEvent(new Event("change"));
    refresh();
    hide();
  }
  function render(query) {
    const q = query.trim().toLowerCase();
    const options = Array.from(select.options);
    const matches = (q ? options.filter((o) => o.textContent.toLowerCase().includes(q)) : options).slice(0, 50);
    highlighted = -1;
    panel.innerHTML = matches.length
      ? matches.map((o, i) => `<button type="button" class="search-suggest-option" data-combo-index="${i}">${o.textContent}</button>`).join("")
      : `<p class="search-suggest-empty">No matches</p>`;
    panel.querySelectorAll("[data-combo-index]").forEach((btn, i) => {
      // mousedown, not click — fires before the input's own blur handler,
      // so the click reliably registers instead of racing a blur-driven
      // panel close.
      btn.onmousedown = (event) => {
        event.preventDefault();
        commit(matches[i]);
      };
    });
    panel.classList.remove("hidden");
  }
  input.addEventListener("input", () => render(input.value));
  input.addEventListener("focus", () => {
    // Selects the existing committed label so typing immediately replaces
    // it instead of appending after it (e.g. "All companies" + "a" typed
    // becoming the literal text "All companiesa" and matching nothing).
    input.select();
    render("");
  });
  input.addEventListener("blur", hide);
  input.addEventListener("keydown", (event) => {
    const rows = () => Array.from(panel.querySelectorAll("[data-combo-index]"));
    if (event.key === "Escape") {
      hide();
      refresh();
      input.blur();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const items = rows();
      if (!items.length) return;
      highlighted = event.key === "ArrowDown" ? Math.min(highlighted + 1, items.length - 1) : Math.max(highlighted - 1, 0);
      items.forEach((el, i) => el.classList.toggle("active", i === highlighted));
      items[highlighted].scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      event.preventDefault();
      const items = rows();
      if (highlighted >= 0 && items[highlighted]) items[highlighted].dispatchEvent(new Event("mousedown"));
    }
  });
  refresh();
  return { refresh };
}

// Phone-number fields (Company/Supplier "Contact phone") — digits only,
// capped at 10, enforced as the user types rather than relying on
// maxlength alone (maxlength caps character COUNT but still lets letters/
// symbols through up to that count; this strips anything non-digit too,
// including on paste).
function wirePhoneDigitsOnly(inputId) {
  const input = $(inputId);
  input.addEventListener("input", () => {
    const digits = input.value.replace(/\D/g, "").slice(0, 10);
    if (digits !== input.value) input.value = digits;
  });
}
["company-contact-phone", "supplier-contact-phone"].forEach(wirePhoneDigitsOnly);

// The input-time filter above can only ever leave 0-10 digits in the
// field, so the one remaining bad state is an INCOMPLETE number (1-9
// digits) — this catches that at submit time rather than silently saving
// a partial phone number. Empty stays fine (the field is optional).
function invalidPhone(inputId) {
  const value = $(inputId).value.trim();
  if (value && value.length !== 10) {
    toast("Phone number must be exactly 10 digits.", "bad");
    $(inputId).focus();
    return true;
  }
  return false;
}

async function api(path, { method = "GET", body, auth = false } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    if (!state.accessToken) {
      toast("Access token required. Login first.", "bad");
      return { status: 0, data: {} };
    }
    headers.Authorization = `Bearer ${state.accessToken}`;
  }
  const response = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    toast(data.message || data.error_code || "Request failed.", "bad");
  }
  return { status: response.status, data };
}

// Both also hide #restore-curtain — see the top-of-file curtain check
// and .restore-curtain in styles.css. Once either of these runs, the
// real outcome (still signed in vs. the session having actually
// expired) is known, so nothing needs the curtain covering the screen
// any more.
function showGate() {
  $("gate").classList.remove("hidden");
  $("app").classList.add("hidden");
  $("restore-curtain").classList.add("hidden");
}

function showApp() {
  $("gate").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("restore-curtain").classList.add("hidden");
}

function renderUser(payload) {
  const claims = payload.claims || {};
  facts("user-fields", [
    ["email", payload.email, "mail"],
    ["full_name", payload.full_name, "user"],
    ["role", payload.role, "shield"],
    ["company_id", payload.company_id, "building"],
    ["is_active", payload.is_active ? "true" : "false", "activity"],
    ["login_count", payload.login_count, "hash"],
  ]);
  facts("claim-fields", [
    ["user_id / sub", claims.user_id, "hash"],
    ["roles", claims.roles, "shield"],
    ["company_id", claims.company_id, "building"],
    ["jti", claims.jti, "link"],
    ["issued_at (iat)", claims.iat, "clock"],
    ["expiry (exp)", claims.exp, "clock"],
    ["token_type", claims.token_type, "access"],
  ]);
  $("who-name").textContent = payload.full_name || payload.email;
  $("who-meta").textContent = payload.email;
  $("role-badge").textContent = humanize(payload.role);
  $("role-badge").className = `badge role-${payload.role}`;
  const firstName = (payload.full_name || payload.email || "").split(/\s|@/)[0];
  $("who-first-name").textContent = firstName ? `, ${firstName}` : "";
}

async function loadMe() {
  const result = await api("/api/v1/auth/me", { auth: true });
  if (result.status !== 200) {
    if (result.status === 401) {
      toast(result.data.error_code || "Access token rejected.", "bad");
      clearSession();
    }
    return false;
  }
  state.user = result.data.data;
  // Persist here, not just inside reloadPage() — this is the one place
  // every path that establishes a valid session (login, the "Refresh
  // access token" button, and restoreSession() itself) always passes
  // through. Without it, a plain browser refresh (not one of this app's
  // own reloadPage() calls) right after logging in — before any
  // create/update/delete had a chance to persist the session first —
  // found sessionStorage empty and bounced back to the login gate even
  // though the in-memory session was still perfectly valid.
  persistSession();
  renderUser(state.user);
  showApp();
  // Admin-only sidebar nav items and their sections (Users, Companies,
  // Employees, Suppliers, Assets, Audit log, plus the KPI strip) all share
  // this one class — toggle it here instead of gating a single wrapper, now
  // that each resource is its own top-level sidebar destination.
  document.querySelectorAll(".admin-only").forEach((el) => {
    el.classList.toggle("hidden", state.user.role !== "admin");
  });
  // loadAdmin() and loadSessions() don't depend on each other — run them
  // concurrently instead of one after another. With every action now
  // triggering a full reload (see reloadPage()), this chain runs on
  // every single edit, so its latency directly determines how "slow" the
  // whole app feels.
  const tasks = [loadSessions()];
  if (state.user.role === "admin") tasks.push(loadAdmin());
  await Promise.all(tasks);
  return true;
}

let usersCache = [];

// RBAC (Module 2): role is one of admin/operator/read_only — there is no
// "user" role in app/core/roles.py. This used to be a binary Make
// admin/Make user toggle where "Make user" sent role:"user" and always
// 400'd against AUTH_INVALID_ROLE (found by clicking it during frontend
// testing). A real 3-way select lets every role actually be assigned and
// exercises the full permission matrix, not just admin-vs-not.
// A lock is only "in effect" while locked_until is both set and still in
// the future — login_user clears it (via reset_failed_logins/
// record_successful_login) on the next successful attempt, but a past
// locked_until can otherwise sit on the row until that happens, and
// should read as unlocked-already, not still-locked.
function isUserLocked(user) {
  if (!user.locked_until) return false;
  // The User model's timestamp columns are naive DateTime (no
  // timezone=True — see app/models/user.py), stored/compared as UTC on
  // the backend but serialized with no timezone marker at all. A
  // timezone-less ISO string is parsed as LOCAL time by `new Date(...)`,
  // not UTC — in any timezone ahead/behind UTC that silently mis-times
  // this exact comparison. Appending "Z" when one isn't already present
  // forces the correct UTC interpretation without needing a backend
  // model change.
  const raw = user.locked_until;
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`;
  return new Date(iso) > new Date();
}

function renderUsersTable(items) {
  $("users-table").innerHTML = table(
    ["full_name", "email", "role", "status", "logins", "last_login_at", "action"],
    items.length
      ? items
          .map((user) => {
            const locked = isUserLocked(user);
            return `<tr>
          <td>${user.full_name || "—"}</td>
          <td>${user.email}</td>
          <td>${humanize(user.role)}</td>
          <td><span class="status-pill ${locked ? "bad" : "good"}">${locked ? "Locked" : "Active"}</span></td>
          <td>${user.login_count}</td>
          <td>${fmt(user.last_login_at)}</td>
          <td class="row-actions">
            <div class="row-actions-group">
              <select data-role-select="${user.id}">
                <option value="admin" ${user.role === "admin" ? "selected" : ""}>admin</option>
                <option value="operator" ${user.role === "operator" ? "selected" : ""}>operator</option>
                <option value="read_only" ${user.role === "read_only" ? "selected" : ""}>read_only</option>
              </select>
              <button data-role-apply="${user.id}">${icon("check")}Apply</button>
            </div>
            ${locked ? `<div class="row-actions-group"><button data-unlock-user="${user.id}">${icon("unlock")}Unlock</button></div>` : ""}
          </td>
        </tr>`;
          })
          .join("")
      : null,
    "No users match this search."
  );
  $("users-table").querySelectorAll("[data-role-apply]").forEach((button) => {
    button.onclick = async () => {
      const id = button.getAttribute("data-role-apply");
      const role = $("users-table").querySelector(`[data-role-select="${id}"]`).value;
      if (!(await confirmModal(`Change this user's role to ${role}?`))) return;
      const result = await api(`/api/v1/auth/users/${id}/role`, {
        method: "PATCH",
        body: { role },
        auth: true,
      });
      if (result.status === 200) {
        toast(`Role changed to ${role}.`, "ok");
        reloadPage();
      }
    };
  });
  $("users-table").querySelectorAll("[data-unlock-user]").forEach((button) => {
    button.onclick = async () => {
      if (!(await confirmModal("Unlock this account?"))) return;
      const result = await api(`/api/v1/auth/users/${button.getAttribute("data-unlock-user")}/unlock`, {
        method: "POST",
        auth: true,
      });
      if (result.status === 200) {
        toast("Account unlocked.", "ok");
        reloadPage();
      }
    };
  });
}

$("users-search").oninput = () => {
  renderUsersTable(filterItems(usersCache, $("users-search").value, ["full_name"]));
};
wireSearchSuggestions("users-search", "users-search-suggest", () => usersCache, ["full_name"], (u) => u.full_name, (u) => u.role);
wireCsvExport("btn-export-users", {
  headers: ["full_name", "email", "role", "status", "logins", "last_login_at"],
  getFilteredItems: () => filterItems(usersCache, $("users-search").value, ["full_name"]),
  rowMapper: (u) => [u.full_name, u.email, humanize(u.role), isUserLocked(u) ? "Locked" : "Active", u.login_count, fmt(u.last_login_at)],
  filenamePrefix: "users",
});

// Display-only cap for the Overview KPI strip — the real counts (used
// everywhere else: Users/Sessions tables, pagination totals, etc.) are
// untouched, this just keeps these two tiles from showing a huge raw
// number. registered_users and active_sessions were the two called out
// as too large; total_logins/failed_logins are shown as-is. Once capped,
// the exact value doesn't disappear — it's still set as a hover title
// (setKpi below) so it's one hover away, not just "100+" forever.
function capDisplay(value, max = 100) {
  return value > max ? `${max}+` : String(value);
}

// Sets a KPI tile's text to its (possibly capped) display value, and its
// title attribute to the exact number whenever capping actually kicked in
// — so "100+" isn't a dead end, just collapsed by default.
function setKpi(elementId, value) {
  const el = $(elementId);
  el.textContent = capDisplay(value);
  el.title = value > 100 ? `Exact: ${value}` : "";
}

async function loadAdmin() {
  $("users-table").innerHTML = skeletonTable();
  $("recent-activity-table").innerHTML = skeletonTable(4);
  const result = await api("/api/v1/auth/overview", { auth: true });
  if (result.status !== 200) return;
  const data = result.data.data;
  setKpi("kpi-users", data.registered_users);
  $("kpi-logins").textContent = data.total_logins;
  setKpi("kpi-active", data.active_sessions);
  $("kpi-failed").textContent = data.failed_logins;
  // isUserLocked() already exists (the Users CSV export uses it) —
  // data.users already carries locked_until per user, so this is a pure
  // client-side count, no new backend call.
  setKpi("kpi-locked", data.users.filter(isUserLocked).length);
  usersCache = data.users;
  renderUsersTable(filterItems(usersCache, $("users-search").value, ["full_name"]));
  // data.sessions is the same "last 25 logins, newest first" list the
  // Sessions page fetches separately — already present on this response,
  // previously never rendered anywhere.
  renderRecentActivityTable(data.sessions || []);

  // Foundation Core management panels (Companies/Employees/Suppliers/Assets/
  // Departments/Job Roles) live alongside Users under the same admin-only
  // gate — load them once here so switching tabs is instant rather than
  // firing a request per click. Companies/Suppliers/Assets/Audit
  // logs/Departments/Job Roles don't depend on each other, so fetch them
  // concurrently instead of one after another — Employees is the one
  // exception (it needs the default company filter set from the companies
  // list first, and its form's dropdowns need Departments/Job Roles
  // already populated), so it waits for the whole group.
  const [companies] = await Promise.all([
    loadCompanies(),
    loadSuppliers(),
    loadManufacturers(),
    loadAssetModels(),
    loadAssets(),
    loadAuditLogs(),
    loadEvents(),
    loadDepartments(),
    loadJobRoles(),
    loadApplications(),
  ]);
  // No auto-selected company here — "All companies" (the dropdown's
  // empty default value) is the Employees page's own default view now,
  // not a fallback state before a company gets picked. Auto-picking
  // companies[0] used to mean landing on whatever company happened to
  // sort first — including an empty, brand-new test company — making the
  // page look broken by default.
  await loadEmployees();
}

// Overview page's own "Recent activity" card — a plain, unpaginated
// preview (see the hint text next to it in index.html) of the same
// session data the Sessions page shows in full, not a competing table
// with its own search/filter/revoke actions.
function renderRecentActivityTable(sessions) {
  $("recent-activity-table").innerHTML = table(
    ["user", "logged in", "ip address", "status"],
    sessions.length
      ? sessions
          .slice(0, 8)
          .map(
            (s) => `<tr>
          <td>${s.email}</td>
          <td>${fmt(s.created_at)}</td>
          <td>${s.ip_address || "—"}</td>
          <td><span class="status-pill ${s.is_revoked ? "bad" : "good"}">${s.is_revoked ? "Revoked" : "Active"}</span></td>
        </tr>`
          )
          .join("")
      : null,
    "No logins recorded yet."
  );
}

let sessionsCache = [];

async function loadSessions() {
  $("sessions-table").innerHTML = skeletonTable();
  const result = await api("/api/v1/auth/sessions", { auth: true });
  const rows = result.data.data;
  sessionsCache = result.status === 200 && Array.isArray(rows) ? rows : [];
  renderSessionsTable(filterItems(sessionsCache, $("sessions-search").value, ["id", "ip_address"]));
}

function renderSessionsTable(rows) {
  $("sessions-table").innerHTML = table(
    ["id", "created_at", "expires_at", "last_used_at", "ip_address", "is_revoked", ""],
    rows.length
      ? rows
          .map(
            (row) => `<tr>
          <td>${row.id}</td>
          <td>${fmt(row.created_at)}</td>
          <td>${fmt(row.expires_at)}</td>
          <td>${fmt(row.last_used_at)}</td>
          <td>${row.ip_address || "—"}</td>
          <td>${row.is_revoked ? "true" : "false"}</td>
          <td><button data-revoke="${row.id}">${icon("revoke")}Revoke session</button></td>
        </tr>`
          )
          .join("")
      : null,
    "No sessions match this search."
  );
  $("sessions-table").querySelectorAll("[data-revoke]").forEach((button) => {
    button.onclick = async () => {
      if (!(await confirmModal("Revoke this session?"))) return;
      const result = await api(`/api/v1/auth/sessions/${button.getAttribute("data-revoke")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Session revoked.", "ok");
        // Revoking a session only invalidates that session's own tokens
        // (see app/services/auth_service.py::_revoke_session_fully) — it
        // does NOT touch this browser's current access token unless the
        // row you just revoked happens to be this browser's own session.
        // Confirm which case it was with a lightweight authed call rather
        // than assuming every revoke logs you out: if the token is still
        // good, reload right here; only clear the session if it turns out
        // this browser's own token was the one just revoked.
        const stillSignedIn = await api("/api/v1/auth/me", { auth: true });
        if (stillSignedIn.status === 401) {
          clearSession();
        } else {
          reloadPage();
        }
      }
    };
  });
}

$("sessions-search").oninput = () => {
  renderSessionsTable(filterItems(sessionsCache, $("sessions-search").value, ["id", "ip_address"]));
};
wireSearchSuggestions(
  "sessions-search",
  "sessions-search-suggest",
  () => sessionsCache,
  ["id", "ip_address"],
  (s) => s.ip_address || String(s.id), // must stay a raw matched-field value — the label click fills the box with this and re-filters against it
  (s) => `session #${s.id}`
);
wireCsvExport("btn-export-sessions", {
  headers: ["id", "created_at", "expires_at", "last_used_at", "ip_address", "is_revoked"],
  getFilteredItems: () => filterItems(sessionsCache, $("sessions-search").value, ["id", "ip_address"]),
  rowMapper: (s) => [s.id, fmt(s.created_at), fmt(s.expires_at), fmt(s.last_used_at), s.ip_address || "", s.is_revoked ? "true" : "false"],
  filenamePrefix: "sessions",
});

/* ============ Companies / Employees / Suppliers management ============ */

const EMPLOYEE_TRANSITIONS = {
  onboarded: ["active", "exited"],
  active: ["on_leave", "exited"],
  on_leave: ["active", "exited"],
  exited: [],
};
const SUPPLIER_TRANSITIONS = {
  onboarded: ["approved"],
  approved: ["suspended"],
  suspended: ["approved"],
};

function statusOptions(transitions, current) {
  const next = transitions[current] || [];
  if (!next.length) return `<option value="">(terminal)</option>`;
  return `<option value="">Change status to&hellip;</option>` + next.map((s) => `<option value="${s}">${s}</option>`).join("");
}

/* ---- Sidebar navigation ---- */
// Moves the single persistent theme-picker element (#theme-picker-mount)
// into whichever page's own heading row is currently visible — every
// page-head/.overview-header carries a [data-theme-slot] placeholder for
// exactly this. Replaces the old fixed breadcrumb+theme-picker bar that
// used to sit in its own row above every page (a separate line, always in
// the same spot regardless of section) — this way the picker always reads
// as part of THIS page's own heading instead of a page-independent
// toolbar. appendChild on an already-in-DOM node moves it rather than
// cloning it, so its event listeners (wired once in initThemeSystem())
// keep working no matter how many times it relocates.
function relocateThemePicker(section) {
  const slot = section.querySelector("[data-theme-slot]");
  const mount = $("theme-picker-mount");
  if (slot && mount) slot.appendChild(mount);
}

// Shared by nav clicks and by session-restore-after-reload below, so both
// paths show/hide sections, highlight the right nav item, move the theme
// picker into the new section's heading, and keep the URL hash in sync
// the exact same way. Returns false if sectionId doesn't exist (or its
// nav item isn't there), so callers can fall back to Overview.
function activateSection(sectionId, { updateHash = true } = {}) {
  const navItem = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
  const section = $(sectionId);
  if (!navItem || !section) return false;
  document.querySelectorAll(".nav-item").forEach((t) => t.classList.remove("on"));
  document.querySelectorAll(".page-section").forEach((p) => p.classList.add("hidden"));
  // A "+ New X" / row Edit button opens its page's .entity-form by
  // removing "hidden" — nothing ever put it back once the user
  // navigated away without hitting Cancel or finishing the submit, so
  // e.g. clicking a Department's "View employees" could land back on
  // the Employees page with a stray "New employee" form still sitting
  // open from an earlier visit, mid-edit state and all. Every page
  // should start clean when you arrive at it, same as a fresh load.
  document.querySelectorAll(".entity-form").forEach((f) => f.classList.add("hidden"));
  navItem.classList.add("on");
  section.classList.remove("hidden");
  relocateThemePicker(section);
  if (updateHash) {
    const hash = "#" + (SECTION_TO_HASH[sectionId] || "overview");
    if (location.hash !== hash) location.hash = hash;
  }
  return true;
}

document.querySelectorAll(".nav-item").forEach((item) => {
  item.onclick = () => activateSection(item.getAttribute("data-section"));
});

// The browser's own Back/Forward buttons (top-left of the browser
// window) are this app's "back navigation" — every nav click already
// pushes a real history entry by changing location.hash (see
// activateSection() above), so Back already has somewhere to go. What
// was missing: nothing listened for the hash changing back on its own,
// so Back/Forward moved the URL while the visible page stayed frozen on
// whatever section was already showing. This is the fix, using the
// app's existing hash router (HASH_TO_SECTION/activateSection) — no
// separate navigation system. currentHashSection() already falls back to
// "section-overview" for any hash it doesn't recognize (including the
// empty hash you get from going back past the first entry), so landing
// with no real previous page in history safely lands on Overview instead
// of doing nothing.
window.addEventListener("hashchange", () => {
  activateSection(currentHashSection(), { updateHash: false });
});

/* ---- Companies ---- */
let companiesCache = [];
let companiesTotal = 0;

async function loadCompanies() {
  $("companies-table").innerHTML = skeletonTable();
  // Deactivating a company must not make it disappear with no way back —
  // always fetch inactive ones too and show status inline (see the
  // status-pill in renderCompaniesTable), instead of hiding them behind a
  // toggle the way Departments/Job Roles/Employees historically did.
  //
  // Sort and Type filter both go server-side (not just re-ordering/
  // narrowing the already-fetched page client-side) — the list is capped
  // at 100 rows, so a client-side-only filter/sort could silently miss
  // real matches sitting past that window, the same bug the Assets search
  // had before it got a server-side `search` param.
  const [sortBy, sortDir] = ($("companies-sort").value || "created_at:desc").split(":");
  const typeFilter = $("companies-type-filter").value;
  const result = await api(
    `/api/v1/companies?limit=100&include_inactive=true&sort_by=${sortBy}&sort_dir=${sortDir}${
      typeFilter ? `&company_type=${typeFilter}` : ""
    }`,
    { auth: true }
  );
  if (result.status !== 200) return [];
  const items = result.data.data.items || [];
  companiesCache = items;
  companiesTotal = result.data.data.total ?? items.length;
  renderCompaniesTable(filterItems(companiesCache, $("companies-search").value, ["name", "company_type", "contact_email"]));
  // Dropdowns list every loaded company regardless of the search box —
  // search only narrows what's visible in the table. The company picker
  // for browsing an existing company's employees includes inactive
  // companies (you can still look at who used to work there); the "New
  // employee" form's Company* field only offers active ones, since the
  // backend rejects creating an employee under an inactive company.
  // Just the name — company names are already unique (the backend
  // rejects a duplicate with a 409), so a "(#123)" suffix wasn't
  // disambiguating anything, just cluttering every company reference in
  // the Employees page's Company filter/form dropdown.
  const options = items.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  const activeOptions = items
    .filter((c) => c.is_active)
    .map((c) => `<option value="${c.id}">${c.name}</option>`)
    .join("");
  const filter = $("employee-company-filter");
  const formSelect = $("employee-company-id");
  const prevFilter = filter.value;
  // "All companies" is a real, selectable option here (empty value — see
  // loadEmployees(), which omits company_id from the request entirely
  // when this is selected) and the page's own default, not just a
  // fallback for "no companies exist yet".
  filter.innerHTML = `<option value="">All companies</option>` + options;
  // A blank placeholder as the first option here too (see the identical
  // fix on asset-supplier-id) — without one, opening "New employee" with
  // no Company filter selected auto-picked whichever company happened to
  // load first, instead of leaving the field empty until chosen.
  formSelect.innerHTML = activeOptions
    ? `<option value="">Select a company…</option>` + activeOptions
    : `<option value="">No active companies yet</option>`;
  if (prevFilter && items.some((c) => String(c.id) === prevFilter)) filter.value = prevFilter;
  employeeCompanyFilterCombo.refresh();
  return items;
}

$("companies-search").oninput = () => {
  renderCompaniesTable(filterItems(companiesCache, $("companies-search").value, ["name", "company_type", "contact_email"]));
};
wireSearchSuggestions(
  "companies-search",
  "companies-search-suggest",
  () => companiesCache,
  ["name", "company_type", "contact_email"],
  (c) => c.name,
  (c) => c.company_type
);
$("companies-sort").onchange = loadCompanies;
$("companies-type-filter").onchange = loadCompanies;
wireCsvExport("btn-export-companies", {
  headers: ["id", "name", "type", "email", "phone", "active"],
  getFilteredItems: () => filterItems(companiesCache, $("companies-search").value, ["name", "company_type", "contact_email"]),
  rowMapper: (c) => [c.id, c.name, humanize(c.company_type), c.contact_email || "", c.contact_phone || "", c.is_active ? "Active" : "Inactive"],
  filenamePrefix: "companies",
});

function renderCompaniesTable(items) {
  $("companies-table").innerHTML = table(
    ["id", "name", "type", "email", "phone", "active", ""],
    items.length
      ? items
          .map(
            (c) => `<tr>
          <td>${c.id}</td>
          <td>${c.name}</td>
          <td>${humanize(c.company_type)}</td>
          <td>${fmt(c.contact_email)}</td>
          <td>${fmt(c.contact_phone)}</td>
          <td><span class="status-pill ${c.is_active ? "good" : "bad"}">${c.is_active ? "Active" : "Inactive"}</span></td>
          <td class="row-actions">
            <!-- Editing a deactivated company isn't offered any more —
                 Reactivate is the only way back in, same idea as an
                 exited employee below. Omitted outright (not just
                 reserved) since nothing follows it in this row to
                 misalign. -->
            ${c.is_active ? `<button data-edit-company="${c.id}">${icon("edit")}Edit</button>` : ""}
            ${
              c.is_active
                ? `<button class="danger" data-deactivate-company="${c.id}">${icon("deactivate")}Deactivate</button>`
                : `<button data-reactivate-company="${c.id}">${icon("reactivate")}Reactivate</button>`
            }
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No companies match this search."
  );
  $("companies-table").querySelectorAll("[data-edit-company]").forEach((btn) => {
    btn.onclick = () => {
      const c = items.find((x) => String(x.id) === btn.getAttribute("data-edit-company"));
      if (!c) return;
      $("company-edit-id").value = c.id;
      $("company-name").value = c.name;
      $("company-type").value = c.company_type;
      $("company-address").value = c.address || "";
      $("company-contact-email").value = c.contact_email || "";
      $("company-contact-phone").value = c.contact_phone || "";
      $("company-type").disabled = true;
      setButtonLabel($("company-submit-btn"), "check", "Save changes");
      $("form-company").classList.remove("hidden");
      $("form-company").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  $("companies-table").querySelectorAll("[data-deactivate-company]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Deactivate this company?"))) return;
      const result = await api(`/api/v1/companies/${btn.getAttribute("data-deactivate-company")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Company deactivated.", "ok");
        reloadPage();
      }
    };
  });
  $("companies-table").querySelectorAll("[data-reactivate-company]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Reactivate this company?"))) return;
      const result = await api(`/api/v1/companies/${btn.getAttribute("data-reactivate-company")}/reactivate`, {
        method: "PATCH",
        auth: true,
      });
      if (result.status === 200) {
        toast("Company reactivated.", "ok");
        reloadPage();
      }
    };
  });
}

function resetCompanyForm() {
  $("form-company").reset();
  $("company-edit-id").value = "";
  $("company-type").disabled = false;
  setButtonLabel($("company-submit-btn"), "plus", "Create company");
}

$("btn-new-company").onclick = () => {
  resetCompanyForm();
  $("form-company").classList.remove("hidden");
};
$("company-cancel-btn").onclick = () => {
  $("form-company").classList.add("hidden");
  resetCompanyForm();
};
$("form-company").onsubmit = async (event) => {
  event.preventDefault();
  if (invalidPhone("company-contact-phone")) return;
  const editId = $("company-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this company?" : "Create this company?"))) return;
  await withLoading($("company-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const body = editId
      ? {
          name: $("company-name").value,
          address: $("company-address").value || null,
          contact_email: $("company-contact-email").value || null,
          contact_phone: $("company-contact-phone").value || null,
        }
      : {
          name: $("company-name").value,
          company_type: $("company-type").value,
          address: $("company-address").value || null,
          contact_email: $("company-contact-email").value || null,
          contact_phone: $("company-contact-phone").value || null,
        };
    const result = await api(editId ? `/api/v1/companies/${editId}` : "/api/v1/companies", {
      method: editId ? "PUT" : "POST",
      body,
      auth: true,
    });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Company updated." : "Company created.", "ok");
      $("form-company").classList.add("hidden");
      resetCompanyForm();
      reloadPage();
    }
  });
};

/* ---- Employees ---- */
let employeesCache = [];
let employeesTotal = 0;

async function loadEmployees() {
  $("employees-table").innerHTML = skeletonTable();
  // Empty selection = "All companies" — the page's own default, shown
  // before any company is explicitly picked (matching how Companies/
  // Departments/Job Roles/Assets/Suppliers all show everything up front
  // rather than an empty list until a filter is touched). company_id is
  // simply omitted from the request in that case; the backend decides
  // what "all" means for the caller (every company for an admin, just
  // their own for anyone else — see employee_service.list_company_employees).
  const companyId = $("employee-company-filter").value;
  const companyQuery = companyId ? `&company_id=${companyId}` : "";
  const includeExited = $("employee-include-exited").checked;
  const department = $("employee-department-filter").value;
  const departmentQuery = department ? `&department=${encodeURIComponent(department)}` : "";
  const result = await api(
    `/api/v1/employees?limit=100&include_exited=${includeExited}${companyQuery}${departmentQuery}`,
    { auth: true }
  );
  if (result.status !== 200) {
    $("employees-table").innerHTML = `<p class="empty">Could not load employees (${result.data.error_code || result.status}).</p>`;
    return;
  }
  employeesCache = result.data.data.items || [];
  employeesTotal = result.data.data.total ?? employeesCache.length;
  renderEmployeesTable(filterItems(employeesCache, $("employees-search").value, EMPLOYEE_SEARCH_FIELDS));
}

// Kept as one shared list rather than repeated inline arrays — mirrors the
// fields app/repositories/employee_repository.py's _filtered() search
// actually matches against server-side (name, email, employee_code,
// designation), plus department/status for the client-side-only
// filter/suggestions/export paths below.
const EMPLOYEE_SEARCH_FIELDS = ["full_name", "email", "employee_code", "designation", "department", "status"];

$("employees-search").oninput = () => {
  renderEmployeesTable(filterItems(employeesCache, $("employees-search").value, EMPLOYEE_SEARCH_FIELDS));
};
wireSearchSuggestions(
  "employees-search",
  "employees-search-suggest",
  () => employeesCache,
  EMPLOYEE_SEARCH_FIELDS,
  (e) => e.full_name,
  (e) => e.email
);
wireCsvExport("btn-export-employees", {
  headers: ["id", "name", "company", "email", "employee_code", "designation", "department", "phone_number", "linkedin_url", "address", "status", "manager_id"],
  getFilteredItems: () => filterItems(employeesCache, $("employees-search").value, EMPLOYEE_SEARCH_FIELDS),
  rowMapper: (e) => [
    e.id,
    e.full_name,
    companyName(e.company_id),
    e.email,
    e.employee_code || "",
    e.designation || "",
    e.department || "",
    e.phone_number || "",
    e.linkedin_url || "",
    e.address || "",
    humanize(e.status),
    e.manager_id ?? "",
  ],
  filenamePrefix: "employees",
});

// "Link user" ties this HR record to a login account (a row from the
// Users page) so that when that person signs in, the app can find their
// employee profile. It used to ask for a raw numeric user id with no way
// to look one up — replaced with a dropdown of that employee's own
// company's users (minus anyone already linked to a different employee),
// so picking a name is all it takes.
function linkUserControl(e) {
  if (e.user_id) {
    const linkedUser = usersCache.find((u) => u.id === e.user_id);
    const label = `Linked: ${linkedUser ? linkedUser.full_name || linkedUser.email : `user #${e.user_id}`}`;
    // title="" so the compact/truncated version (see #employees-table
    // .row-actions-group .hint in styles.css) still gives the full name
    // back on hover — same "clip + tooltip" treatment as the data columns.
    return `<span class="hint" style="margin:0;" title="${escapeHtml(label)}">${escapeHtml(label)}</span>`;
  }
  const linkedElsewhere = new Set(
    employeesCache.filter((other) => other.user_id && other.id !== e.id).map((other) => other.user_id)
  );
  const eligible = usersCache.filter((u) => u.company_id === e.company_id && !linkedElsewhere.has(u.id));
  if (!eligible.length) {
    const label = "No unlinked users in this company";
    return `<span class="hint" style="margin:0;" title="${label}">${label}</span>`;
  }
  return `
    <select data-link-select="${e.id}">
      <option value="">Link to user…</option>
      ${eligible.map((u) => `<option value="${u.id}">${u.full_name || u.email} (${u.email})</option>`).join("")}
    </select>
    <button class="icon-btn" data-link-apply="${e.id}" title="Link to this user">${icon("link")}</button>
  `;
}

// Resolves an employee's company_id to its name via the already-loaded
// companiesCache — needed once the Employees page can show rows from
// every company at once ("All companies"), so a row's company is
// identifiable without a second lookup.
function companyName(companyId) {
  const company = companiesCache.find((c) => c.id === companyId);
  return company ? company.name : `#${companyId}`;
}

// Resolves a manager id to a scannable name instead of a bare number —
// looks in the currently-rendered list first (the common case), falling
// back to the full page cache (a manager who exists but got filtered out
// of this particular view/page), and finally just "#id" if neither has
// them (e.g. a stale id after that employee was hard-deleted outside the API).
function employeeManagerLabel(managerId, items) {
  if (!managerId) return "—";
  const manager =
    items.find((x) => x.id === managerId) || employeesCache.find((x) => x.id === managerId);
  return manager ? manager.full_name : `#${managerId}`;
}

// A capped-width, ellipsis-truncated table cell with the untruncated
// original as a native title="" tooltip — for the plain-text columns
// (Role, Department, Manager) that get their width from the table's own
// table-layout:fixed columns (see #employees-table table in styles.css),
// so no per-cell max-width is needed here, just overflow handling.
// Escaped: every value passed in is employee-entered free text.
function tdClip(value) {
  const display = value === null || value === undefined || value === "" ? "—" : value;
  const safe = escapeHtml(String(display));
  return `<td class="td-clip" title="${safe}">${safe}</td>`;
}

function renderEmployeesTable(items) {
  $("employees-table").innerHTML = table(
    ["id", "employee", "designation", "department", "status", "manager", ""],
    items.length
      ? items
          .map((e) => {
            const safeName = escapeHtml(e.full_name);
            const isExited = e.status === "exited";
            const roleLabel = e.designation || "—";
            const managerLabel = employeeManagerLabel(e.manager_id, items);
            return `<tr>
          <td>${e.id}</td>
          <td><span class="emp-name cell-clip" title="${safeName}">${safeName}</span></td>
          ${tdClip(roleLabel)}
          ${tdClip(e.department)}
          <td><span class="status-pill ${isExited ? "bad" : "good"}">${humanize(e.status)}</span></td>
          ${tdClip(managerLabel)}
          <td class="row-actions">
            <div class="row-actions-group">
              <!-- Everything the table itself no longer shows as its own
                   column (email, company, employee code, designation,
                   phone, LinkedIn, photo, linked user, application access)
                   lives in the View modal instead (see
                   openEmployeeViewModal()). -->
              <button class="icon-btn" data-view-employee="${e.id}" title="View details">${icon("view")}</button>
              <!-- An exited employee is done — no reason to still offer a
                   way to look up their application access or edit their
                   record, so both go reserved (visually hidden, not
                   removed, so every row's Actions column stays the same
                   width) once terminal. Status change/link-user/delete
                   moved into the More panel below rather than needing
                   their own reserved slots here (see
                   renderEmployeeMorePanel()). -->
              <button class="icon-btn${isExited ? " reserved" : ""}" data-view-access="${e.id}" title="Access to">${icon("access")}</button>
              <button class="icon-btn${isExited ? " reserved" : ""}" data-edit-employee="${e.id}" title="Edit">${icon("edit")}</button>
              <button class="icon-btn" data-more-employee="${e.id}" title="More actions">${icon("more")}</button>
            </div>
          </td>
        </tr>`;
          })
          .join("")
      : null,
    "No employees match this search."
  );
  $("employees-table").querySelectorAll("[data-view-employee]").forEach((btn) => {
    btn.onclick = (event) => {
      event.stopPropagation();
      const e = items.find((x) => String(x.id) === btn.getAttribute("data-view-employee"));
      if (!e) return;
      openEmployeeViewModal(e);
    };
  });
  $("employees-table").querySelectorAll("[data-view-access]").forEach((btn) => {
    btn.onclick = (event) => {
      event.stopPropagation();
      const e = items.find((x) => String(x.id) === btn.getAttribute("data-view-access"));
      if (!e) return;
      toggleEmployeeAccessPanel(btn, e);
    };
  });
  $("employees-table").querySelectorAll("[data-more-employee]").forEach((btn) => {
    btn.onclick = (event) => {
      event.stopPropagation();
      const e = items.find((x) => String(x.id) === btn.getAttribute("data-more-employee"));
      if (!e) return;
      toggleEmployeeMorePanel(btn, e);
    };
  });
  $("employees-table").querySelectorAll("[data-edit-employee]").forEach((btn) => {
    btn.onclick = () => {
      const e = items.find((x) => String(x.id) === btn.getAttribute("data-edit-employee"));
      if (!e) return;
      $("employee-edit-id").value = e.id;
      // Editable — a wrong company picked at creation is a real, fixable
      // mistake, not a locked field. Changing it re-populates the Manager
      // dropdown below for the newly-selected company (see the
      // employee-company-id onchange handler further down).
      $("employee-company-id").disabled = false;
      $("employee-company-id").value = e.company_id;
      // The dropdown's own options are active-companies-only (correct for
      // "New employee" — the backend rejects creating under an inactive
      // one), but an employee already on the books can belong to a
      // company that's since been deactivated. The .value assignment
      // above silently no-ops when e.company_id isn't one of the current
      // options, leaving the field blank instead of showing the
      // employee's real company — so add it in for this one edit if
      // that's what just happened.
      if ($("employee-company-id").value !== String(e.company_id)) {
        const current = companiesCache.find((c) => c.id === e.company_id);
        const option = document.createElement("option");
        option.value = String(e.company_id);
        option.textContent = current ? `${current.name} (inactive)` : `#${e.company_id}`;
        $("employee-company-id").prepend(option);
        $("employee-company-id").value = e.company_id;
      }
      $("employee-first-name").value = e.first_name;
      $("employee-last-name").value = e.last_name;
      $("employee-email").value = e.email;
      $("employee-code").value = e.employee_code || "";
      setSelectOrOther($("employee-designation-select"), $("employee-designation-other-wrap"), $("employee-designation-other"), e.designation || "");
      $("employee-phone-number").value = e.phone_number || "";
      $("employee-photo-reference").value = e.photo_reference || "";
      $("employee-photo-file").value = "";
      showEmployeePhotoPreview(e.photo_reference || "");
      $("employee-linkedin-url").value = e.linkedin_url || "";
      setSelectOrOther($("employee-address-select"), $("employee-address-other-wrap"), $("employee-address-other"), e.address || "");
      setSelectOrOther($("employee-department-select"), $("employee-department-other-wrap"), $("employee-department-other"), e.department || "");
      // Self excluded — the backend also rejects self-as-manager and any
      // cycle this would create (see _validate_manager_assignment).
      fillManagerOptions(items, e.id);
      $("employee-manager-id").value = e.manager_id || "";
      populateEmployeeApplicationCheckboxes(applicationsCache, e.application_ids || []);
      $("employee-applications-panel").classList.add("hidden");
      setButtonLabel($("employee-submit-btn"), "check", "Save changes");
      $("form-employee").classList.remove("hidden");
      $("form-employee").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
}

// Designation / Department are a fixed dropdown list plus an "Other" option
// that reveals a free-text field — covers the common cases with a click,
// without losing the ability to enter something not on the list (or to
// edit an existing record whose value predates the list).
function setSelectOrOther(selectEl, otherWrapEl, otherInputEl, value) {
  const options = Array.from(selectEl.options).map((o) => o.value);
  if (value && options.includes(value)) {
    selectEl.value = value;
    otherWrapEl.classList.add("hidden");
    otherInputEl.value = "";
  } else if (value) {
    selectEl.value = "__other__";
    otherWrapEl.classList.remove("hidden");
    otherInputEl.value = value;
  } else {
    selectEl.value = "";
    otherWrapEl.classList.add("hidden");
    otherInputEl.value = "";
  }
}
function getSelectOrOther(selectEl, otherInputEl) {
  return selectEl.value === "__other__" ? otherInputEl.value.trim() : selectEl.value;
}
// Employee photo: the file input is the only thing a user interacts with —
// employee-photo-reference (hidden) holds the actual saved value (a URL),
// filled in the moment a pick finishes uploading. Uploading immediately on
// pick, rather than waiting for the form's own Save/Create, means the
// user sees it worked (or didn't) right away, and the rest of the form's
// submit payload never needs to carry the raw file at all — it just reads
// employee-photo-reference like it always has.
function showEmployeePhotoPreview(url) {
  const wrap = $("employee-photo-preview-wrap");
  const img = $("employee-photo-preview");
  if (url) {
    img.src = withBasePath(url);
    wrap.classList.remove("hidden");
  } else {
    img.src = "";
    wrap.classList.add("hidden");
  }
}

async function uploadEmployeePhoto(file) {
  const status = $("employee-photo-status");
  if (!state.accessToken) {
    status.textContent = "Access token required. Login first.";
    return;
  }
  status.textContent = "Uploading…";
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/v1/uploads/employee-photo", {
      method: "POST",
      headers: { Authorization: `Bearer ${state.accessToken}` },
      // No Content-Type here — the browser sets multipart/form-data with
      // the correct boundary itself only when Content-Type is left unset.
      body: formData,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      status.textContent = data.message || data.error_code || "Upload failed.";
      toast(status.textContent, "bad");
      $("employee-photo-file").value = "";
      return;
    }
    $("employee-photo-reference").value = data.data.url;
    showEmployeePhotoPreview(data.data.url);
    status.textContent = "Uploaded.";
  } catch (err) {
    status.textContent = "Upload failed — network error.";
    toast(status.textContent, "bad");
    $("employee-photo-file").value = "";
  }
}

$("employee-photo-file").onchange = () => {
  const file = $("employee-photo-file").files[0];
  if (file) uploadEmployeePhoto(file);
};

$("employee-department-select").onchange = () => {
  $("employee-department-other-wrap").classList.toggle("hidden", $("employee-department-select").value !== "__other__");
};
$("employee-designation-select").onchange = () => {
  $("employee-designation-other-wrap").classList.toggle("hidden", $("employee-designation-select").value !== "__other__");
};
$("employee-address-select").onchange = () => {
  $("employee-address-other-wrap").classList.toggle("hidden", $("employee-address-select").value !== "__other__");
};
// "Application access" is a dropdown, not an always-open checkbox list —
// .app-access-panel starts hidden; the trigger toggles it, any click
// outside the whole .app-access-dropdown closes it, and the trigger's own
// label always reflects the current selection (see
// updateApplicationsSummary below), same idea as a native <select>
// showing its current value.
$("employee-applications-trigger").onclick = (event) => {
  event.preventDefault();
  $("employee-applications-panel").classList.toggle("hidden");
};
document.addEventListener("click", (event) => {
  const dropdown = $("employee-applications-trigger").closest(".app-access-dropdown");
  if (dropdown && !dropdown.contains(event.target)) {
    $("employee-applications-panel").classList.add("hidden");
  }
});
function updateApplicationsSummary() {
  const count = getCheckedApplicationIds().length;
  $("employee-applications-summary").textContent =
    count === 0 ? "No applications selected" : count === 1 ? "1 application selected" : `${count} applications selected`;
}
$("employee-application-checkboxes").addEventListener("change", (event) => {
  if (event.target.matches("[data-application-checkbox]")) updateApplicationsSummary();
});
$("employee-applications-select-all").onclick = () => {
  $("employee-application-checkboxes")
    .querySelectorAll("[data-application-checkbox]")
    .forEach((input) => (input.checked = true));
  updateApplicationsSummary();
};
$("employee-applications-clear-all").onclick = () => {
  $("employee-application-checkboxes")
    .querySelectorAll("[data-application-checkbox]")
    .forEach((input) => (input.checked = false));
  updateApplicationsSummary();
};

// Fills the Manager (reports to) select from a given employee list — used
// both on create (a fresh fetch for whichever company is picked) and edit
// (the already-loaded page cache, self excluded). Manager must be in the
// same company as the employee — the backend enforces this too (and
// rejects any cycle) via _validate_manager_assignment.
function fillManagerOptions(employees, excludeEmployeeId) {
  const managerSelect = $("employee-manager-id");
  managerSelect.disabled = false;
  managerSelect.innerHTML =
    `<option value="">(none)</option>` +
    employees
      .filter((other) => String(other.id) !== String(excludeEmployeeId))
      .map((other) => `<option value="${other.id}">${other.full_name} (#${other.id})</option>`)
      .join("");
}

// Company-scoped, so it needs that company's employee list — reuses
// employeesCache when it already happens to be for the same company (the
// common case: the Employees page's own Company filter), otherwise fetches
// it fresh rather than showing another company's people as candidates.
async function populateManagerSelectForCompany(companyId, excludeEmployeeId) {
  const managerSelect = $("employee-manager-id");
  if (!companyId) {
    managerSelect.innerHTML = `<option value="">(none)</option>`;
    managerSelect.disabled = true;
    return;
  }
  if (String($("employee-company-filter").value) === String(companyId)) {
    fillManagerOptions(employeesCache, excludeEmployeeId);
    return;
  }
  const result = await api(`/api/v1/employees?company_id=${companyId}&limit=100`, { auth: true });
  fillManagerOptions(result.status === 200 ? result.data.data.items || [] : [], excludeEmployeeId);
}
$("employee-company-id").onchange = () => {
  populateManagerSelectForCompany($("employee-company-id").value, $("employee-edit-id").value);
};

function resetEmployeeForm() {
  $("form-employee").reset();
  $("employee-edit-id").value = "";
  $("employee-department-other-wrap").classList.add("hidden");
  $("employee-designation-other-wrap").classList.add("hidden");
  $("employee-address-other-wrap").classList.add("hidden");
  $("employee-photo-reference").value = "";
  $("employee-photo-status").textContent = "";
  showEmployeePhotoPreview("");
  $("employee-company-id").disabled = false;
  const filterCompany = $("employee-company-filter").value;
  if (filterCompany) $("employee-company-id").value = filterCompany;
  populateManagerSelectForCompany($("employee-company-id").value, "");
  populateEmployeeApplicationCheckboxes(applicationsCache, []);
  $("employee-applications-panel").classList.add("hidden");
  setButtonLabel($("employee-submit-btn"), "plus", "Create employee");
}

$("btn-new-employee").onclick = () => {
  resetEmployeeForm();
  $("form-employee").classList.remove("hidden");
};
$("employee-cancel-btn").onclick = () => {
  $("form-employee").classList.add("hidden");
  resetEmployeeForm();
};
$("employee-company-filter").onchange = loadEmployees;
const employeeCompanyFilterCombo = wireSearchableSelect("employee-company-filter", "employee-company-filter-input", "employee-company-filter-panel");
$("employee-include-exited").onchange = loadEmployees;
$("employee-department-filter").onchange = loadEmployees;
$("form-employee").onsubmit = async (event) => {
  event.preventDefault();
  const editId = $("employee-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this employee?" : "Create this employee?"))) return;
  await withLoading($("employee-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const result = editId
      ? await api(`/api/v1/employees/${editId}`, {
          method: "PUT",
          body: {
            company_id: Number($("employee-company-id").value),
            first_name: $("employee-first-name").value,
            last_name: $("employee-last-name").value,
            email: $("employee-email").value,
            employee_code: $("employee-code").value || null,
            designation: getSelectOrOther($("employee-designation-select"), $("employee-designation-other")) || null,
            phone_number: $("employee-phone-number").value || null,
            photo_reference: $("employee-photo-reference").value || null,
            linkedin_url: $("employee-linkedin-url").value || null,
            address: getSelectOrOther($("employee-address-select"), $("employee-address-other")) || null,
            department: getSelectOrOther($("employee-department-select"), $("employee-department-other")) || null,
            manager_id: $("employee-manager-id").value ? Number($("employee-manager-id").value) : null,
            application_ids: getCheckedApplicationIds(),
          },
          auth: true,
        })
      : await api("/api/v1/employees", {
          method: "POST",
          body: {
            company_id: Number($("employee-company-id").value),
            first_name: $("employee-first-name").value,
            last_name: $("employee-last-name").value,
            email: $("employee-email").value,
            employee_code: $("employee-code").value || null,
            designation: getSelectOrOther($("employee-designation-select"), $("employee-designation-other")) || null,
            phone_number: $("employee-phone-number").value || null,
            photo_reference: $("employee-photo-reference").value || null,
            linkedin_url: $("employee-linkedin-url").value || null,
            address: getSelectOrOther($("employee-address-select"), $("employee-address-other")) || null,
            department: getSelectOrOther($("employee-department-select"), $("employee-department-other")) || null,
            manager_id: $("employee-manager-id").value ? Number($("employee-manager-id").value) : null,
            application_ids: getCheckedApplicationIds(),
          },
          auth: true,
        });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Employee updated." : "Employee created.", "ok");
      $("form-employee").classList.add("hidden");
      resetEmployeeForm();
      reloadPage();
    }
  });
};

/* ---- Departments / Job Roles (master data feeding the Employee form's
 * Department / Job role dropdowns) — previously a fixed, hardcoded option
 * list; now a real admin-managed list, mirroring the Companies pattern
 * (soft-delete via is_active, not a status state machine like
 * Supplier/Asset/Employee). Both entities are structurally identical, so
 * the two blocks below are near-duplicates of each other rather than a
 * shared abstraction — matches this codebase's existing convention of one
 * dedicated block per entity (see Companies/Suppliers/Assets) over a
 * generic "master list" component. ---- */

// Rebuilds a <select>'s options from a live master-data list, keeping
// whichever of its first ("" / "(none)") and last ("__other__") sentinel
// options are already there, and restoring the previously selected value
// if it still exists in the new list (or is the sentinel itself).
function populateMasterDataSelect(selectEl, items) {
  const prev = selectEl.value;
  const optionEls = Array.from(selectEl.options);
  const firstSentinel = optionEls[0];
  const lastSentinel = optionEls[optionEls.length - 1];
  const middle = items.map((item) => `<option value="${item.name}">${item.name}</option>`).join("");
  selectEl.innerHTML = firstSentinel.outerHTML + middle + lastSentinel.outerHTML;
  if (prev && Array.from(selectEl.options).some((o) => o.value === prev)) {
    selectEl.value = prev;
  }
}

// Application access is a multi-pick (any number checked at once), unlike
// Job role/Department's single-pick <select> above — a checkbox grid
// instead of populateMasterDataSelect's <option> list. Only ever offers
// active applications, same "dropdown only shows active items" rule
// loadJobRoles()/loadDepartments() already follow. One flat list, not
// grouped by category — applications keep whatever order
// applicationsCache is already in (alphabetical by name, same as the
// Applications admin table).
function populateEmployeeApplicationCheckboxes(applications, checkedIds = []) {
  const container = $("employee-application-checkboxes");
  const active = applications.filter((a) => a.is_active);
  const checked = new Set(checkedIds.map(Number));

  container.innerHTML = active.length
    ? active
        .map(
          (a) => `<label class="checkbox">
        <input type="checkbox" value="${a.id}" data-application-checkbox ${checked.has(a.id) ? "checked" : ""} />
        ${a.name}
      </label>`
        )
        .join("")
    : `<p class="empty">No applications defined yet.</p>`;
  updateApplicationsSummary();
}

function getCheckedApplicationIds() {
  return Array.from($("employee-application-checkboxes").querySelectorAll("[data-application-checkbox]:checked")).map(
    (input) => Number(input.value)
  );
}

let departmentsCache = []; // whatever the table is currently showing (search/parent/inactive filters applied)
let allDepartmentsCache = []; // every department, unfiltered — backs every dropdown + the detail modal's hierarchy lookups
// Every employee across every company, unfiltered — backs the Manager
// dropdown on this form. Deliberately its own fetch/cache, not a reuse of
// employeesCache (declared on the Employees page below): that one tracks
// whatever company the Employees page's own filter is currently set to,
// which would silently narrow this global picker to one company's people
// depending on what someone last did on a different page.
let allEmployeesCache = [];

function departmentParentFilterQuery() {
  const value = $("departments-parent-filter").value;
  if (value === "__top_level__") return "&top_level_only=true";
  if (value) return `&parent_department_id=${value}`;
  return "";
}

// Every id (transitively) below departmentId, via allDepartmentsCache — used
// to keep the "Parent department" picker from offering a department's own
// descendant as its parent (the server rejects it too, via
// app.core.graph_utils.creates_cycle, but catching it in the dropdown is a
// better experience than a submit-time error).
function departmentDescendantIds(departmentId) {
  const childrenOf = {};
  allDepartmentsCache.forEach((d) => {
    if (d.parent_department_id != null) {
      (childrenOf[d.parent_department_id] ||= []).push(d.id);
    }
  });
  const result = new Set();
  const stack = [departmentId];
  while (stack.length) {
    const current = stack.pop();
    (childrenOf[current] || []).forEach((childId) => {
      if (!result.has(childId)) {
        result.add(childId);
        stack.push(childId);
      }
    });
  }
  return result;
}

function populateDepartmentParentSelect() {
  const select = $("department-parent-select");
  const editId = $("department-edit-id").value;
  const prev = select.value;
  const excluded = editId ? departmentDescendantIds(Number(editId)) : new Set();
  if (editId) excluded.add(Number(editId));
  const options = allDepartmentsCache.filter((d) => d.is_active && !excluded.has(d.id));
  select.innerHTML =
    '<option value="">(none — top level)</option>' +
    options.map((d) => `<option value="${d.id}">${d.name}</option>`).join("");
  if (prev && Array.from(select.options).some((o) => o.value === prev)) select.value = prev;
}

function populateDepartmentsParentFilter() {
  const select = $("departments-parent-filter");
  const prev = select.value;
  const deptOptions = allDepartmentsCache
    .filter((d) => d.is_active)
    .map((d) => `<option value="${d.id}">Belongs to: ${d.name}</option>`)
    .join("");
  select.innerHTML =
    '<option value="">All</option><option value="__top_level__">Top-level only</option>' + deptOptions;
  if (prev && Array.from(select.options).some((o) => o.value === prev)) select.value = prev;
}

function populateEmployeeDepartmentFilter() {
  const select = $("employee-department-filter");
  const prev = select.value;
  const options = allDepartmentsCache
    .filter((d) => d.is_active)
    .map((d) => `<option value="${d.name}">${d.name}</option>`)
    .join("");
  select.innerHTML = '<option value="">All</option>' + options;
  if (prev && Array.from(select.options).some((o) => o.value === prev)) select.value = prev;
}

async function loadDepartments() {
  $("departments-table").innerHTML = skeletonTable();
  const includeInactive = $("departments-include-inactive").checked;
  const [tableResult, allResult, employeesResult] = await Promise.all([
    api(
      `/api/v1/departments?limit=100&include_inactive=${includeInactive}${departmentParentFilterQuery()}`,
      { auth: true }
    ),
    // A second, always-unfiltered fetch — dropdowns (Employee form's
    // Department select, this form's Parent select, the parent filter
    // itself) and the detail modal's children lookup all need the
    // complete list regardless of what the table above is filtered to.
    api("/api/v1/departments?limit=100&include_inactive=true", { auth: true }),
    // Backs this form's own Manager dropdown — see allEmployeesCache above
    // for why it's a dedicated fetch rather than reusing employeesCache.
    api("/api/v1/employees?limit=100", { auth: true }),
  ]);
  if (tableResult.status !== 200) return [];
  departmentsCache = tableResult.data.data.items || [];
  if (allResult.status === 200) allDepartmentsCache = allResult.data.data.items || [];
  if (employeesResult.status === 200) allEmployeesCache = employeesResult.data.data.items || [];
  renderDepartmentsTable(filterItems(departmentsCache, $("departments-search").value, ["name"]));
  populateMasterDataSelect(
    $("employee-department-select"),
    allDepartmentsCache.filter((d) => d.is_active)
  );
  populateDepartmentParentSelect();
  populateDepartmentsParentFilter();
  populateEmployeeDepartmentFilter();
  populateDepartmentManagerSelect();
  return departmentsCache;
}

// Manager dropdown for the Department form — every employee across every
// company (see allEmployeesCache), labeled with its id to disambiguate any
// two people sharing a name. The option's value is the plain name only
// (what actually gets stored as Department.manager_name — see that
// model's docstring for why this stays a free-text field, not a real
// employee_id FK), so the "(#id)" suffix shows up in the dropdown list
// only, never in the saved value or anywhere it's displayed afterwards.
function populateDepartmentManagerSelect() {
  const select = $("department-manager-select");
  const prev = select.value;
  const middle = allEmployeesCache
    .map((e) => `<option value="${e.full_name}">${e.full_name} (#${e.id})</option>`)
    .join("");
  select.innerHTML = `<option value="">(none)</option>${middle}<option value="__other__">Other (type below)…</option>`;
  if (prev && Array.from(select.options).some((o) => o.value === prev)) select.value = prev;
}
$("department-manager-select").onchange = () => {
  $("department-manager-other-wrap").classList.toggle("hidden", $("department-manager-select").value !== "__other__");
};

$("departments-search").oninput = () => {
  renderDepartmentsTable(filterItems(departmentsCache, $("departments-search").value, ["name"]));
};
wireSearchSuggestions("departments-search", "departments-search-suggest", () => departmentsCache, ["name"], (d) => d.name, (d) => (d.is_active ? "" : "inactive"));
wireCsvExport("btn-export-departments", {
  headers: ["id", "name", "belongs_to", "status", "people"],
  getFilteredItems: () => filterItems(departmentsCache, $("departments-search").value, ["name"]),
  rowMapper: (d) => [d.id, d.name, d.parent_department_name || "", d.is_active ? "Active" : "Inactive", d.employee_count ?? 0],
  filenamePrefix: "departments",
});

$("departments-include-inactive").onchange = loadDepartments;
$("departments-parent-filter").onchange = loadDepartments;

function renderDepartmentsTable(items) {
  $("departments-table").innerHTML = table(
    ["id", "name", "belongs to", "status", "people", ""],
    items.length
      ? items
          .map(
            (d) => `<tr>
          <td>${d.id}</td>
          <td>${d.name}</td>
          <td>${d.parent_department_name || "—"}</td>
          <td><span class="status-pill ${d.is_active ? "good" : "bad"}">${d.is_active ? "Active" : "Inactive"}</span></td>
          <td>${d.employee_count ?? 0}</td>
          <td class="row-actions">
            <div class="row-actions-group">
              <button data-view-department="${d.id}">${icon("view")}View</button>
              <!-- View (read-only) stays available either way — only
                   Edit goes away once deactivated. -->
              ${d.is_active ? `<button data-edit-department="${d.id}">${icon("edit")}Edit</button>` : ""}
              ${
                d.is_active
                  ? `<button class="danger" data-deactivate-department="${d.id}">${icon("deactivate")}Deactivate</button>`
                  : `<button data-reactivate-department="${d.id}">${icon("reactivate")}Reactivate</button>`
              }
            </div>
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No departments match this search."
  );
  $("departments-table").querySelectorAll("[data-view-department]").forEach((btn) => {
    btn.onclick = () => {
      const d = items.find((x) => String(x.id) === btn.getAttribute("data-view-department"));
      if (d) openDepartmentDetail(d);
    };
  });
  $("departments-table").querySelectorAll("[data-edit-department]").forEach((btn) => {
    btn.onclick = () => {
      const d = items.find((x) => String(x.id) === btn.getAttribute("data-edit-department"));
      if (!d) return;
      $("department-edit-id").value = d.id;
      $("department-name").value = d.name;
      setSelectOrOther($("department-manager-select"), $("department-manager-other-wrap"), $("department-manager-other"), d.manager_name || "");
      $("department-description").value = d.description || "";
      setButtonLabel($("department-submit-btn"), "check", "Save changes");
      populateDepartmentParentSelect();
      $("department-parent-select").value = d.parent_department_id || "";
      $("form-department").classList.remove("hidden");
      $("form-department").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  $("departments-table").querySelectorAll("[data-deactivate-department]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Deactivate this department?"))) return;
      const result = await api(`/api/v1/departments/${btn.getAttribute("data-deactivate-department")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Department deactivated.", "ok");
        reloadPage();
      }
    };
  });
  $("departments-table").querySelectorAll("[data-reactivate-department]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Reactivate this department?"))) return;
      const result = await api(`/api/v1/departments/${btn.getAttribute("data-reactivate-department")}/reactivate`, {
        method: "PATCH",
        auth: true,
      });
      if (result.status === 200) {
        toast("Department reactivated.", "ok");
        reloadPage();
      }
    };
  });
}

// Employee application-access dropdown — a read-only view of exactly which
// applications a given employee currently has access to (the "Access to"
// button next to Edit/Delete on the Employees table), so checking doesn't
// require opening the edit form and the Application access dropdown. A
// plain dropdown, not a popup: one shared panel (#employee-access-panel),
// repositioned next to whichever row's button triggered it. It's
// position:fixed rather than a normal absolutely-positioned dropdown
// because the Employees table itself scrolls (.table-scroll) — an
// absolute panel would get clipped by that container the moment a row
// near the bottom of the visible area opened it.
// Shared by both dropdown panels below (Access and View) — measure after
// the panel is visible-but-off-position (its innerHTML must already be set
// so it has its real size), then place it flush against the button that
// opened it, like a normal attached dropdown rather than a floating card
// positioned independently of it. Left edge lines up with the button's
// left edge by default; if that would run off the right side of the
// viewport, flip to lining up the panel's *right* edge with the button's
// right edge instead — one edge always touches the button, it never gets
// clamped to some unrelated viewport position. Same idea vertically: flips
// to open above the button instead of below when there isn't room left on
// the page.
function positionDropdownPanel(panel, button) {
  const buttonRect = button.getBoundingClientRect();
  const panelRect = panel.getBoundingClientRect();
  let left = buttonRect.left;
  if (left + panelRect.width > window.innerWidth - 8) left = buttonRect.right - panelRect.width;
  if (left < 8) left = 8;
  const spaceBelow = window.innerHeight - buttonRect.bottom;
  const openAbove = spaceBelow < panelRect.height + 12 && buttonRect.top > panelRect.height + 12;
  panel.style.left = `${left}px`;
  panel.style.top = openAbove ? `${buttonRect.top - panelRect.height - 6}px` : `${buttonRect.bottom + 6}px`;
}

function hideEmployeeAccessPanel() {
  const panel = $("employee-access-panel");
  panel.classList.add("hidden");
  delete panel.dataset.forEmployee;
}
function toggleEmployeeAccessPanel(button, employee) {
  const panel = $("employee-access-panel");
  const alreadyOpenForThis = panel.dataset.forEmployee === String(employee.id) && !panel.classList.contains("hidden");
  if (alreadyOpenForThis) {
    hideEmployeeAccessPanel();
    return;
  }
  hideEmployeeMorePanel();
  const names = employee.application_names || [];
  // Empty case gets its own compact styling (.access-empty, not the
  // table-wide .empty) — a small box with small text, not the same size
  // panel as a real, populated access list.
  panel.classList.toggle("is-empty", !names.length);
  panel.innerHTML = names.length
    ? `<ul class="access-chip-list">${names.map((n) => `<li class="access-chip">${n}</li>`).join("")}</ul>`
    : `<p class="access-empty">No access</p>`;
  panel.dataset.forEmployee = employee.id;
  panel.classList.remove("hidden");
  positionDropdownPanel(panel, button);
}

// Row-actions overflow ("More" button) — status change, linking a user
// account, and Delete used to sit inline in every row; they're rendered
// fresh into this one shared panel per click instead (same anchored,
// position:fixed pattern as the Access panel above), so their handlers
// are (re)wired every time it opens rather than once at table-render time.
function hideEmployeeMorePanel() {
  const panel = $("employee-more-panel");
  panel.classList.add("hidden");
  delete panel.dataset.forEmployee;
}
function renderEmployeeMorePanel(employee) {
  const isExited = employee.status === "exited";
  // Exited is terminal — no entry in EMPLOYEE_TRANSITIONS to change to,
  // and Delete would just re-apply the same exited status — so both are
  // dropped for a terminal row rather than shown as dead controls.
  // Linking a user account still makes sense regardless of status.
  const statusSection = isExited
    ? `<p class="more-panel-note">Exited — no further status changes.</p>`
    : `<div class="more-panel-section">
        <span class="more-panel-label">Change status</span>
        <div class="more-panel-row">
          <select data-status-select="${employee.id}">${statusOptions(EMPLOYEE_TRANSITIONS, employee.status)}</select>
          <button class="icon-btn" data-status-apply="${employee.id}" title="Apply status change">${icon("check")}</button>
        </div>
      </div>`;
  const linkSection = `<div class="more-panel-section">
      <span class="more-panel-label">User account</span>
      <div class="more-panel-row">${linkUserControl(employee)}</div>
    </div>`;
  const deleteSection = isExited
    ? ""
    : `<div class="more-panel-divider"></div>
      <button type="button" class="danger wide" data-delete-employee="${employee.id}">${icon("delete")}Delete employee</button>`;
  return `${statusSection}${linkSection}${deleteSection}`;
}
// (Re)binds click handlers for whatever the panel's own innerHTML just
// got set to (see toggleEmployeeMorePanel()) — the buttons/selects are
// fresh DOM nodes every time it opens, so there's nothing to bind at
// table-render time the way the table's own row buttons are.
function wireEmployeeMorePanelActions(employee) {
  const panel = $("employee-more-panel");
  const statusApply = panel.querySelector("[data-status-apply]");
  if (statusApply) {
    statusApply.onclick = async () => {
      const select = panel.querySelector("[data-status-select]");
      if (!select.value) return;
      if (!(await confirmModal(`Change this employee's status to ${select.value}?`))) return;
      const result = await api(`/api/v1/employees/${employee.id}/status`, {
        method: "PATCH",
        body: { status: select.value },
        auth: true,
      });
      if (result.status === 200) {
        toast(`Status changed to ${select.value}.`, "ok");
        reloadPage();
      }
    };
  }
  const linkApply = panel.querySelector("[data-link-apply]");
  if (linkApply) {
    linkApply.onclick = async () => {
      const select = panel.querySelector("[data-link-select]");
      if (!select.value) {
        toast("Choose a user to link first.", "bad");
        return;
      }
      if (!(await confirmModal("Link this employee to the selected user account?"))) return;
      const result = await api(`/api/v1/employees/${employee.id}/link-user`, {
        method: "PATCH",
        body: { user_id: Number(select.value) },
        auth: true,
      });
      if (result.status === 200) {
        toast("Employee linked to user account.", "ok");
        reloadPage();
      }
    };
  }
  const deleteBtn = panel.querySelector("[data-delete-employee]");
  if (deleteBtn) {
    deleteBtn.onclick = async () => {
      if (!(await confirmModal("Delete this employee?"))) return;
      const result = await api(`/api/v1/employees/${employee.id}`, { method: "DELETE", auth: true });
      if (result.status === 200) {
        toast("Employee soft-deleted (status: exited).", "ok");
        reloadPage();
      }
    };
  }
}
function toggleEmployeeMorePanel(button, employee) {
  const panel = $("employee-more-panel");
  const alreadyOpenForThis = panel.dataset.forEmployee === String(employee.id) && !panel.classList.contains("hidden");
  if (alreadyOpenForThis) {
    hideEmployeeMorePanel();
    return;
  }
  hideEmployeeAccessPanel();
  panel.innerHTML = renderEmployeeMorePanel(employee);
  panel.dataset.forEmployee = employee.id;
  panel.classList.remove("hidden");
  positionDropdownPanel(panel, button);
  wireEmployeeMorePanelActions(employee);
}

// Resolves an employee's linked login account (see linkUserControl()
// above) to a plain display label for the read-only View modal — that
// modal never edits the link, just states it, so it needs a string, not
// linkUserControl()'s own <select>+button markup.
function employeeLinkedUserLabel(employee) {
  if (!employee.user_id) return "Not linked to a user account";
  const user = usersCache.find((u) => u.id === employee.user_id);
  return user ? user.full_name || user.email : `user #${employee.user_id}`;
}

// Profile header at the top of the View modal (see #employee-view-profile
// in index.html) — photo (or a placeholder), name, role, and status at a
// glance before the sectioned facts below it.
function renderEmployeeViewProfile(employee) {
  const roleLine = employee.designation || "—";
  const photo = employee.photo_reference
    ? `<img class="employee-view-photo" src="${escapeHtml(withBasePath(employee.photo_reference))}" alt="" />`
    : `<div class="employee-view-photo employee-view-photo-placeholder">${icon("user")}</div>`;
  $("employee-view-profile").innerHTML = `${photo}<div class="employee-view-identity">
      <div class="employee-view-name">${escapeHtml(employee.full_name)}</div>
      <div class="employee-view-role">${escapeHtml(roleLine)}</div>
      <span class="status-pill ${employee.status === "exited" ? "bad" : "good"}">${humanize(employee.status)}</span>
    </div>`;
}

// Read-only "full profile" modal — see #employee-view-modal in index.html.
// A centered modal (the app's existing .modal-overlay/.modal-card
// pattern — same as openDepartmentDetail()/openAssetDetail()) rather than
// an anchored dropdown panel like Access/More above: a multi-section
// profile needs a header and close control that stay fixed regardless of
// how much content is inside, not one that repositions itself next to
// whichever row button opened it.
function openEmployeeViewModal(employee) {
  hideEmployeeAccessPanel();
  hideEmployeeMorePanel();
  renderEmployeeViewProfile(employee);
  // facts() interpolates its values as-is (see its own definition) — every
  // one of these is free-text an employee record can hold, so each is
  // escaped here first rather than trusting facts() to do it.
  const esc = (v) => (v == null || v === "" ? v : escapeHtml(String(v)));
  facts("employee-view-contact", [
    ["Email", esc(employee.email), "mail"],
    ["Phone", esc(employee.phone_number), "phone"],
    ["LinkedIn", esc(employee.linkedin_url), "link"],
    ["Address", esc(employee.address), "mappin"],
  ]);
  facts("employee-view-work", [
    ["Employee ID", esc(employee.employee_code), "hash"],
    ["Company", esc(companyName(employee.company_id)), "building"],
    ["Department", esc(employee.department), "layers"],
    ["Designation", esc(employee.designation), "briefcase"],
    ["Manager", esc(employeeManagerLabel(employee.manager_id, employeesCache)), "user"],
  ]);
  const accessLabel =
    employee.application_names && employee.application_names.length ? employee.application_names.join(", ") : "No access";
  facts("employee-view-account", [
    ["Linked user", esc(employeeLinkedUserLabel(employee)), "user"],
    ["App access", esc(accessLabel), "shield"],
  ]);
  $("employee-view-modal").classList.remove("hidden");
}
function closeEmployeeViewModal() {
  $("employee-view-modal").classList.add("hidden");
}
$("employee-view-close").onclick = closeEmployeeViewModal;
$("employee-view-modal").onclick = (event) => {
  if (event.target === $("employee-view-modal")) closeEmployeeViewModal();
};

document.addEventListener("click", (event) => {
  const accessPanel = $("employee-access-panel");
  if (!accessPanel.classList.contains("hidden") && !accessPanel.contains(event.target) && !event.target.closest("[data-view-access]")) {
    hideEmployeeAccessPanel();
  }
  const morePanel = $("employee-more-panel");
  if (!morePanel.classList.contains("hidden") && !morePanel.contains(event.target) && !event.target.closest("[data-more-employee]")) {
    hideEmployeeMorePanel();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    hideEmployeeAccessPanel();
    hideEmployeeMorePanel();
    closeEmployeeViewModal();
  }
});
// A fixed-position panel doesn't move with the table's own scroll — close
// it rather than let it drift away from the button that opened it.
// (capture:true so this also catches scroll events on .table-scroll
// itself, which don't bubble to window.)
window.addEventListener("scroll", hideEmployeeAccessPanel, true);
window.addEventListener("resize", hideEmployeeAccessPanel);
window.addEventListener("scroll", hideEmployeeMorePanel, true);
window.addEventListener("resize", hideEmployeeMorePanel);

// Department details modal — a read-only summary (status, manager,
// parent, description, headcount) plus its direct sub-departments and a
// jump into the Employees page filtered to this department. Reuses the
// confirm dialog's .modal-overlay/.modal-card, just wider (see .wide in
// styles.css) since this shows more than a yes/no question.
function openDepartmentDetail(department) {
  $("department-detail-title").textContent = department.name;
  facts("department-detail-facts", [
    ["Status", department.is_active ? "Active" : "Inactive", "activity"],
    ["Manager", department.manager_name || "—", "user"],
    ["Parent department", department.parent_department_name || "(top level)", "link"],
    ["People", department.employee_count ?? 0, "users"],
    ["Description", department.description || "—", "note"],
  ]);
  const children = allDepartmentsCache.filter((d) => d.parent_department_id === department.id);
  $("department-detail-children").innerHTML = children.length
    ? `<p class="hint" style="margin:14px 0 6px;">Sub-departments (${children.length})</p><ul>${children
        .map((c) => `<li>${c.name} — ${c.employee_count ?? 0} ${c.employee_count === 1 ? "person" : "people"}</li>`)
        .join("")}</ul>`
    : "";
  $("department-detail-view-employees").onclick = () => {
    $("department-detail-modal").classList.add("hidden");
    viewDepartmentEmployees(department.name);
  };
  $("department-detail-modal").classList.remove("hidden");
}
$("department-detail-close").onclick = () => $("department-detail-modal").classList.add("hidden");
$("department-detail-modal").onclick = (event) => {
  if (event.target === $("department-detail-modal")) $("department-detail-modal").classList.add("hidden");
};

// Drill-down from a department into its people — jumps to the Employees
// page and applies the Department filter, keeping whatever Company is
// already selected there. If nothing was selected, this lands on "All
// companies" (index 0 in the dropdown — see loadCompanies()), showing
// everyone in this department across every company at once, which is
// exactly what a department drill-down should show.
function viewDepartmentEmployees(departmentName) {
  activateSection("section-employees");
  if (!$("employee-company-filter").value && $("employee-company-filter").options.length) {
    $("employee-company-filter").selectedIndex = 0;
    employeeCompanyFilterCombo.refresh();
  }
  $("employee-department-filter").value = departmentName;
  loadEmployees();
}

function resetDepartmentForm() {
  $("form-department").reset();
  $("department-edit-id").value = "";
  $("department-manager-other-wrap").classList.add("hidden");
  setButtonLabel($("department-submit-btn"), "plus", "Create department");
  populateDepartmentParentSelect();
}

$("btn-new-department").onclick = () => {
  resetDepartmentForm();
  $("form-department").classList.remove("hidden");
};
$("department-cancel-btn").onclick = () => {
  $("form-department").classList.add("hidden");
  resetDepartmentForm();
};
$("form-department").onsubmit = async (event) => {
  event.preventDefault();
  const editId = $("department-edit-id").value;
  const parentValue = $("department-parent-select").value;
  if (!(await confirmModal(editId ? "Save changes to this department?" : "Create this department?"))) return;
  await withLoading($("department-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const result = await api(editId ? `/api/v1/departments/${editId}` : "/api/v1/departments", {
      method: editId ? "PUT" : "POST",
      body: {
        name: $("department-name").value,
        manager_name: getSelectOrOther($("department-manager-select"), $("department-manager-other")) || null,
        description: $("department-description").value || null,
        parent_department_id: parentValue ? Number(parentValue) : null,
      },
      auth: true,
    });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Department updated." : "Department created.", "ok");
      $("form-department").classList.add("hidden");
      resetDepartmentForm();
      reloadPage();
    }
  });
};

let jobRolesCache = [];

async function loadJobRoles() {
  $("job-roles-table").innerHTML = skeletonTable();
  const includeInactive = $("job-roles-include-inactive").checked;
  const result = await api(`/api/v1/job-roles?limit=100&include_inactive=${includeInactive}`, { auth: true });
  if (result.status !== 200) return [];
  jobRolesCache = result.data.data.items || [];
  renderJobRolesTable(filterItems(jobRolesCache, $("job-roles-search").value, ["name"]));
  return jobRolesCache;
}

$("job-roles-search").oninput = () => {
  renderJobRolesTable(filterItems(jobRolesCache, $("job-roles-search").value, ["name"]));
};
wireSearchSuggestions("job-roles-search", "job-roles-search-suggest", () => jobRolesCache, ["name"], (r) => r.name, (r) => (r.is_active ? "" : "inactive"));
wireCsvExport("btn-export-job-roles", {
  headers: ["id", "name", "status", "people"],
  getFilteredItems: () => filterItems(jobRolesCache, $("job-roles-search").value, ["name"]),
  rowMapper: (r) => [r.id, r.name, r.is_active ? "Active" : "Inactive", r.employee_count ?? 0],
  filenamePrefix: "job-roles",
});

$("job-roles-include-inactive").onchange = loadJobRoles;

function renderJobRolesTable(items) {
  $("job-roles-table").innerHTML = table(
    ["id", "name", "status", "people", ""],
    items.length
      ? items
          .map(
            (r) => `<tr>
          <td>${r.id}</td>
          <td>${r.name}</td>
          <td><span class="status-pill ${r.is_active ? "good" : "bad"}">${r.is_active ? "Active" : "Inactive"}</span></td>
          <td>${r.employee_count ?? 0}</td>
          <td class="row-actions">
            <div class="row-actions-group">
              ${r.is_active ? `<button data-edit-job-role="${r.id}">${icon("edit")}Edit</button>` : ""}
              ${
                r.is_active
                  ? `<button class="danger" data-deactivate-job-role="${r.id}">${icon("deactivate")}Deactivate</button>`
                  : `<button data-reactivate-job-role="${r.id}">${icon("reactivate")}Reactivate</button>`
              }
            </div>
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No job roles match this search."
  );
  $("job-roles-table").querySelectorAll("[data-edit-job-role]").forEach((btn) => {
    btn.onclick = () => {
      const r = items.find((x) => String(x.id) === btn.getAttribute("data-edit-job-role"));
      if (!r) return;
      $("job-role-edit-id").value = r.id;
      $("job-role-name").value = r.name;
      setButtonLabel($("job-role-submit-btn"), "check", "Save changes");
      $("form-job-role").classList.remove("hidden");
      $("form-job-role").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  $("job-roles-table").querySelectorAll("[data-deactivate-job-role]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Deactivate this job role?"))) return;
      const result = await api(`/api/v1/job-roles/${btn.getAttribute("data-deactivate-job-role")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Job role deactivated.", "ok");
        reloadPage();
      }
    };
  });
  $("job-roles-table").querySelectorAll("[data-reactivate-job-role]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Reactivate this job role?"))) return;
      const result = await api(`/api/v1/job-roles/${btn.getAttribute("data-reactivate-job-role")}/reactivate`, {
        method: "PATCH",
        auth: true,
      });
      if (result.status === 200) {
        toast("Job role reactivated.", "ok");
        reloadPage();
      }
    };
  });
}

function resetJobRoleForm() {
  $("form-job-role").reset();
  $("job-role-edit-id").value = "";
  setButtonLabel($("job-role-submit-btn"), "plus", "Create job role");
}

$("btn-new-job-role").onclick = () => {
  resetJobRoleForm();
  $("form-job-role").classList.remove("hidden");
};
$("job-role-cancel-btn").onclick = () => {
  $("form-job-role").classList.add("hidden");
  resetJobRoleForm();
};
$("form-job-role").onsubmit = async (event) => {
  event.preventDefault();
  const editId = $("job-role-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this job role?" : "Create this job role?"))) return;
  await withLoading($("job-role-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const result = await api(editId ? `/api/v1/job-roles/${editId}` : "/api/v1/job-roles", {
      method: editId ? "PUT" : "POST",
      body: { name: $("job-role-name").value },
      auth: true,
    });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Job role updated." : "Job role created.", "ok");
      $("form-job-role").classList.add("hidden");
      resetJobRoleForm();
      reloadPage();
    }
  });
};

/* ---- Applications (master data feeding the Employee form's Application
 * access checkboxes) — structurally identical to Job Roles above (same
 * id/name/is_active shape), except the Employee-form side is a multi-pick
 * checkbox grid instead of a single-pick dropdown; see
 * populateEmployeeApplicationCheckboxes / getCheckedApplicationIds above.
 */
let applicationsCache = [];

async function loadApplications() {
  $("applications-table").innerHTML = skeletonTable();
  const includeInactive = $("applications-include-inactive").checked;
  const result = await api(`/api/v1/applications?limit=100&include_inactive=${includeInactive}`, { auth: true });
  if (result.status !== 200) return [];
  applicationsCache = result.data.data.items || [];
  renderApplicationsTable(filterItems(applicationsCache, $("applications-search").value, ["name"]));
  populateEmployeeApplicationCheckboxes(applicationsCache, getCheckedApplicationIds());
  return applicationsCache;
}

$("applications-search").oninput = () => {
  renderApplicationsTable(filterItems(applicationsCache, $("applications-search").value, ["name"]));
};
wireSearchSuggestions(
  "applications-search",
  "applications-search-suggest",
  () => applicationsCache,
  ["name"],
  (a) => a.name,
  (a) => (a.is_active ? "" : "inactive")
);

$("applications-include-inactive").onchange = loadApplications;
wireCsvExport("btn-export-applications", {
  headers: ["id", "name", "category", "status", "people"],
  getFilteredItems: () => filterItems(applicationsCache, $("applications-search").value, ["name"]),
  rowMapper: (a) => [a.id, a.name, a.category || "", a.is_active ? "Active" : "Inactive", a.employee_count ?? 0],
  filenamePrefix: "applications",
});

function renderApplicationsTable(items) {
  $("applications-table").innerHTML = table(
    ["id", "name", "category", "status", "people", ""],
    items.length
      ? items
          .map(
            (a) => `<tr>
          <td>${a.id}</td>
          <td>${a.name}</td>
          <td>${a.category || "—"}</td>
          <td><span class="status-pill ${a.is_active ? "good" : "bad"}">${a.is_active ? "Active" : "Inactive"}</span></td>
          <td>${a.employee_count ?? 0}</td>
          <td class="row-actions">
            <div class="row-actions-group">
              ${a.is_active ? `<button data-edit-application="${a.id}">${icon("edit")}Edit</button>` : ""}
              ${
                a.is_active
                  ? `<button class="danger" data-deactivate-application="${a.id}">${icon("deactivate")}Deactivate</button>`
                  : `<button data-reactivate-application="${a.id}">${icon("reactivate")}Reactivate</button>`
              }
            </div>
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No applications match this search."
  );
  $("applications-table").querySelectorAll("[data-edit-application]").forEach((btn) => {
    btn.onclick = () => {
      const a = items.find((x) => String(x.id) === btn.getAttribute("data-edit-application"));
      if (!a) return;
      $("application-edit-id").value = a.id;
      $("application-name").value = a.name;
      setSelectOrOther(
        $("application-category-select"),
        $("application-category-other-wrap"),
        $("application-category-other"),
        a.category || ""
      );
      setButtonLabel($("application-submit-btn"), "check", "Save changes");
      $("form-application").classList.remove("hidden");
      $("form-application").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  $("applications-table").querySelectorAll("[data-deactivate-application]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Deactivate this application?"))) return;
      const result = await api(`/api/v1/applications/${btn.getAttribute("data-deactivate-application")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Application deactivated.", "ok");
        reloadPage();
      }
    };
  });
  $("applications-table").querySelectorAll("[data-reactivate-application]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Reactivate this application?"))) return;
      const result = await api(`/api/v1/applications/${btn.getAttribute("data-reactivate-application")}/reactivate`, {
        method: "PATCH",
        auth: true,
      });
      if (result.status === 200) {
        toast("Application reactivated.", "ok");
        reloadPage();
      }
    };
  });
}

function resetApplicationForm() {
  $("form-application").reset();
  $("application-edit-id").value = "";
  $("application-category-other-wrap").classList.add("hidden");
  setButtonLabel($("application-submit-btn"), "plus", "Create application");
}

$("application-category-select").onchange = () => {
  $("application-category-other-wrap").classList.toggle(
    "hidden",
    $("application-category-select").value !== "__other__"
  );
};
$("btn-new-application").onclick = () => {
  resetApplicationForm();
  $("form-application").classList.remove("hidden");
};
$("application-cancel-btn").onclick = () => {
  $("form-application").classList.add("hidden");
  resetApplicationForm();
};
$("form-application").onsubmit = async (event) => {
  event.preventDefault();
  const editId = $("application-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this application?" : "Create this application?"))) return;
  await withLoading($("application-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const result = await api(editId ? `/api/v1/applications/${editId}` : "/api/v1/applications", {
      method: editId ? "PUT" : "POST",
      body: {
        name: $("application-name").value,
        category: getSelectOrOther($("application-category-select"), $("application-category-other")) || null,
      },
      auth: true,
    });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Application updated." : "Application created.", "ok");
      $("form-application").classList.add("hidden");
      resetApplicationForm();
      reloadPage();
    }
  });
};

/* ---- Suppliers ---- */
let suppliersCache = [];
let suppliersTotal = 0;

async function loadSuppliers() {
  $("suppliers-table").innerHTML = skeletonTable();
  const status = $("supplier-status-filter").value;
  const result = await api(`/api/v1/suppliers?limit=100${status ? `&status=${status}` : ""}`, { auth: true });
  if (result.status !== 200) return;
  const items = result.data.data.items || [];
  suppliersCache = items;
  suppliersTotal = result.data.data.total ?? items.length;
  renderSuppliersTable(filterItems(suppliersCache, $("suppliers-search").value, ["name", "category", "status"]));
  // Assets reference a supplier by id — show status in the option label so
  // it's obvious at a glance which ones are actually "approved" (the only
  // ones an asset can be registered against; picking an "onboarded" one is
  // still allowed here on purpose, so the 409 SUPPLIER_NOT_APPROVED
  // rejection is something you can actually trigger from the UI).
  const supplierSelect = $("asset-supplier-id");
  const prev = supplierSelect.value;
  // A blank placeholder as the first option — without one, the browser
  // auto-selects the first real supplier the instant this list loads, so
  // "New asset" opened already showing (and would silently submit) some
  // arbitrary supplier nobody actually chose.
  supplierSelect.innerHTML = items.length
    ? `<option value="">Select a supplier…</option>` +
      items.map((s) => `<option value="${s.id}">${s.name} &middot; ${s.status} (#${s.id})</option>`).join("")
    : `<option value="">No suppliers yet</option>`;
  if (prev && items.some((s) => String(s.id) === prev)) supplierSelect.value = prev;
}

$("suppliers-search").oninput = () => {
  renderSuppliersTable(filterItems(suppliersCache, $("suppliers-search").value, ["name", "category", "status"]));
};
wireSearchSuggestions(
  "suppliers-search",
  "suppliers-search-suggest",
  () => suppliersCache,
  ["name", "category", "status"],
  (s) => s.name,
  (s) => s.category
);
wireCsvExport("btn-export-suppliers", {
  headers: ["id", "name", "email", "phone", "category", "terms", "rating", "status"],
  getFilteredItems: () => filterItems(suppliersCache, $("suppliers-search").value, ["name", "category", "status"]),
  rowMapper: (s) => [s.id, s.name, s.contact_email || "", s.contact_phone || "", s.category || "", s.terms || "", s.rating ?? "", humanize(s.status)],
  filenamePrefix: "suppliers",
});

function renderSuppliersTable(items) {
  $("suppliers-table").innerHTML = table(
    ["id", "name", "category", "rating", "status", ""],
    items.length
      ? items
          .map(
            (s) => `<tr>
          <td>${s.id}</td>
          <td>${s.name}</td>
          <td>${fmt(s.category)}</td>
          <td>${fmt(s.rating)}</td>
          <td><span class="status-pill ${s.status === "suspended" ? "bad" : "good"}">${humanize(s.status)}</span></td>
          <td class="row-actions">
            <div class="row-actions-group">
              <button data-edit-supplier="${s.id}">${icon("edit")}Edit</button>
            </div>
            <div class="row-actions-group">
              <select data-status-select="${s.id}">${statusOptions(SUPPLIER_TRANSITIONS, s.status)}</select>
              <button data-status-apply="${s.id}">${icon("check")}Apply</button>
            </div>
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No suppliers match this search."
  );
  $("suppliers-table").querySelectorAll("[data-edit-supplier]").forEach((btn) => {
    btn.onclick = () => {
      const s = items.find((x) => String(x.id) === btn.getAttribute("data-edit-supplier"));
      if (!s) return;
      $("supplier-edit-id").value = s.id;
      $("supplier-name").value = s.name;
      $("supplier-name").disabled = true;
      $("supplier-contact-email").value = s.contact_email || "";
      $("supplier-contact-phone").value = s.contact_phone || "";
      setSelectOrOther(
        $("supplier-category-select"),
        $("supplier-category-other-wrap"),
        $("supplier-category-other"),
        s.category || ""
      );
      setSelectOrOther(
        $("supplier-terms-select"),
        $("supplier-terms-other-wrap"),
        $("supplier-terms-other"),
        s.terms || ""
      );
      // Rounded to a whole number, not the raw value — the select only
      // offers 0-5 (see index.html), but a rating saved before that
      // restriction (or written directly via the API) could still be a
      // decimal like 4.5, which matches none of this select's options and
      // would silently land on "(no rating)" instead of the closest score.
      $("supplier-rating").value = s.rating != null ? String(Math.round(Number(s.rating))) : "";
      setButtonLabel($("supplier-submit-btn"), "check", "Save changes");
      $("form-supplier").classList.remove("hidden");
      $("form-supplier").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  $("suppliers-table").querySelectorAll("[data-status-apply]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.getAttribute("data-status-apply");
      const select = $("suppliers-table").querySelector(`[data-status-select="${id}"]`);
      if (!select.value) return;
      if (!(await confirmModal(`Change this supplier's status to ${select.value}?`))) return;
      const result = await api(`/api/v1/suppliers/${id}/status`, {
        method: "PATCH",
        body: { status: select.value },
        auth: true,
      });
      if (result.status === 200) {
        toast(`Status changed to ${select.value}.`, "ok");
        reloadPage();
      }
    };
  });
}

function resetSupplierForm() {
  $("form-supplier").reset();
  $("supplier-edit-id").value = "";
  $("supplier-name").disabled = false;
  $("supplier-category-other-wrap").classList.add("hidden");
  $("supplier-terms-other-wrap").classList.add("hidden");
  setButtonLabel($("supplier-submit-btn"), "plus", "Create supplier");
}

$("supplier-category-select").onchange = () => {
  $("supplier-category-other-wrap").classList.toggle("hidden", $("supplier-category-select").value !== "__other__");
};
$("supplier-terms-select").onchange = () => {
  $("supplier-terms-other-wrap").classList.toggle("hidden", $("supplier-terms-select").value !== "__other__");
};
$("btn-new-supplier").onclick = () => {
  resetSupplierForm();
  $("form-supplier").classList.remove("hidden");
};
$("supplier-cancel-btn").onclick = () => {
  $("form-supplier").classList.add("hidden");
  resetSupplierForm();
};
$("supplier-status-filter").onchange = loadSuppliers;
$("form-supplier").onsubmit = async (event) => {
  event.preventDefault();
  if (invalidPhone("supplier-contact-phone")) return;
  const editId = $("supplier-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this supplier?" : "Create this supplier?"))) return;
  await withLoading($("supplier-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const rating = $("supplier-rating").value;
    const body = editId
      ? {
          contact_email: $("supplier-contact-email").value || null,
          contact_phone: $("supplier-contact-phone").value || null,
          category: getSelectOrOther($("supplier-category-select"), $("supplier-category-other")) || null,
          terms: getSelectOrOther($("supplier-terms-select"), $("supplier-terms-other")) || null,
          rating: rating === "" ? null : Number(rating),
        }
      : {
          name: $("supplier-name").value,
          contact_email: $("supplier-contact-email").value || null,
          contact_phone: $("supplier-contact-phone").value || null,
          category: getSelectOrOther($("supplier-category-select"), $("supplier-category-other")) || null,
          terms: getSelectOrOther($("supplier-terms-select"), $("supplier-terms-other")) || null,
          rating: rating === "" ? null : Number(rating),
        };
    const result = await api(editId ? `/api/v1/suppliers/${editId}` : "/api/v1/suppliers", {
      method: editId ? "PUT" : "POST",
      body,
      auth: true,
    });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Supplier updated." : "Supplier created.", "ok");
      $("form-supplier").classList.add("hidden");
      resetSupplierForm();
      reloadPage();
    }
  });
};

/* ---- Assets ---- */
const ASSET_TRANSITIONS = {
  registered: ["in_repair", "disposed"],
  in_repair: ["certified", "disposed"],
  certified: ["in_repair", "disposed"],
  disposed: [],
};

let assetsCache = [];
let assetsTotal = 0;

async function loadAssets() {
  $("assets-table").innerHTML = skeletonTable();
  const status = $("asset-status-filter").value;
  const result = await api(`/api/v1/assets?limit=100${status ? `&status=${status}` : ""}`, {
    auth: true,
  });
  if (result.status !== 200) return;
  assetsCache = result.data.data.items || [];
  assetsTotal = result.data.data.total ?? assetsCache.length;
  renderAssetsTable(filterItems(assetsCache, $("assets-search").value, ["asset_tag", "manufacturer", "model", "status"]));
}

$("assets-search").oninput = () => {
  renderAssetsTable(filterItems(assetsCache, $("assets-search").value, ["asset_tag", "manufacturer", "model", "status"]));
};
wireSearchSuggestions(
  "assets-search",
  "assets-search-suggest",
  () => assetsCache,
  ["asset_tag", "manufacturer", "model", "status"],
  (a) => a.asset_tag,
  (a) => [a.manufacturer, a.model].filter(Boolean).join(" ")
);
wireCsvExport("btn-export-assets", {
  headers: ["id", "asset_tag", "manufacturer", "model", "supplier_id", "serial_number", "barcode", "status", "purchase_cost", "current_value", "currency"],
  getFilteredItems: () => filterItems(assetsCache, $("assets-search").value, ["asset_tag", "manufacturer", "model", "status"]),
  rowMapper: (a) => [
    a.id,
    a.asset_tag,
    a.manufacturer,
    a.model,
    a.supplier_id,
    a.serial_number || "",
    a.barcode_value || "",
    humanize(a.status),
    a.purchase_cost ?? "",
    a.current_value ?? "",
    a.currency || "",
  ],
  filenamePrefix: "assets",
});

function renderAssetsTable(items) {
  $("assets-table").innerHTML = table(
    ["id", "asset_tag", "manufacturer / model", "supplier_id", "status", ""],
    items.length
      ? items
          .map(
            (a) => `<tr>
          <td>${a.id}</td>
          <td class="text-mono-id">${a.asset_tag}</td>
          <td>${a.manufacturer} ${a.model}</td>
          <td>${a.supplier_id}</td>
          <td><span class="status-pill ${a.status === "disposed" ? "bad" : "good"}">${humanize(a.status)}</span></td>
          <td class="row-actions">
            <div class="row-actions-group">
              <button data-view-asset="${a.id}">${icon("view")}View</button>
              <!-- Disposed is a hard terminal state (no Reactivate exists
                   for assets, unlike Companies/Departments/etc.) — Edit is
                   just gone once disposed, not reserved, since there's
                   nothing after it in this row to misalign. -->
              ${a.status === "disposed" ? "" : `<button data-edit-asset="${a.id}">${icon("edit")}Edit</button>`}
              <!-- Disposed is terminal — Dispose here would just set the
                   already-disposed status again, a dead control. Kept in
                   the DOM and only visually hidden (not omitted) so this
                   row's column widths stay identical to every other row's
                   regardless of status. -->
              <button class="danger${a.status === "disposed" ? " reserved" : ""}" data-delete-asset="${a.id}">${icon("delete")}Dispose</button>
            </div>
            <!-- No entry in ASSET_TRANSITIONS for "disposed" — a
                 "(terminal)" dropdown + Apply would be a dead control next
                 to a status that will never change again. Same
                 reserved-space treatment as above. -->
            <div class="row-actions-group${a.status === "disposed" ? " reserved" : ""}">
              <select data-status-select="${a.id}">${statusOptions(ASSET_TRANSITIONS, a.status)}</select>
              <button data-status-apply="${a.id}">${icon("check")}Apply</button>
            </div>
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No assets match this filter."
  );
  $("assets-table").querySelectorAll("[data-view-asset]").forEach((btn) => {
    btn.onclick = () => {
      const a = items.find((x) => String(x.id) === btn.getAttribute("data-view-asset"));
      if (a) openAssetDetail(a);
    };
  });
  $("assets-table").querySelectorAll("[data-edit-asset]").forEach((btn) => {
    btn.onclick = () => {
      const a = items.find((x) => String(x.id) === btn.getAttribute("data-edit-asset"));
      if (!a) return;
      populateAssetForm(a);
    };
  });
  $("assets-table").querySelectorAll("[data-status-apply]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.getAttribute("data-status-apply");
      const select = $("assets-table").querySelector(`[data-status-select="${id}"]`);
      if (!select.value) return;
      if (!(await confirmModal(`Change this asset's status to ${select.value}?`))) return;
      const result = await api(`/api/v1/assets/${id}/status`, {
        method: "PATCH",
        body: { status: select.value },
        auth: true,
      });
      if (result.status === 200) {
        toast(`Status changed to ${select.value}.`, "ok");
        reloadPage();
      }
    };
  });
  $("assets-table").querySelectorAll("[data-delete-asset]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Dispose this asset?"))) return;
      const result = await api(`/api/v1/assets/${btn.getAttribute("data-delete-asset")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Asset disposed (soft-deleted, terminal).", "ok");
        reloadPage();
      }
    };
  });
}

function populateAssetForm(a) {
  $("asset-edit-id").value = a.id;
  $("asset-tag").value = a.asset_tag;
  $("asset-tag").disabled = true; // immutable per AssetUpdateRequest
  $("asset-supplier-id").value = a.supplier_id;
  $("asset-supplier-id").disabled = true; // source supplier doesn't change after intake
  setSelectOrOther($("asset-manufacturer-select"), $("asset-manufacturer-other-wrap"), $("asset-manufacturer-other"), a.manufacturer || "");
  setSelectOrOther($("asset-model-select"), $("asset-model-other-wrap"), $("asset-model-other"), a.model || "");
  $("asset-serial-number").value = a.serial_number || "";
  $("asset-barcode").value = a.barcode_value || "";
  $("asset-purchase-cost").value = a.purchase_cost ?? "";
  $("asset-current-value").value = a.current_value ?? "";
  $("asset-currency").value = a.currency || "";
  setButtonLabel($("asset-submit-btn"), "check", "Save changes");
  $("form-asset").classList.remove("hidden");
  $("form-asset").scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetAssetForm() {
  $("form-asset").reset();
  $("asset-edit-id").value = "";
  $("asset-tag").disabled = false;
  $("asset-supplier-id").disabled = false;
  $("asset-manufacturer-other-wrap").classList.add("hidden");
  $("asset-model-other-wrap").classList.add("hidden");
  setButtonLabel($("asset-submit-btn"), "plus", "Register asset");
}

$("asset-manufacturer-select").onchange = () => {
  $("asset-manufacturer-other-wrap").classList.toggle("hidden", $("asset-manufacturer-select").value !== "__other__");
};
$("asset-model-select").onchange = () => {
  $("asset-model-other-wrap").classList.toggle("hidden", $("asset-model-select").value !== "__other__");
};
$("btn-new-asset").onclick = () => {
  resetAssetForm();
  $("form-asset").classList.remove("hidden");
};
$("asset-cancel-btn").onclick = () => {
  $("form-asset").classList.add("hidden");
  resetAssetForm();
};
$("asset-status-filter").onchange = loadAssets;
$("form-asset").onsubmit = async (event) => {
  event.preventDefault();
  const manufacturer = getSelectOrOther($("asset-manufacturer-select"), $("asset-manufacturer-other"));
  const model = getSelectOrOther($("asset-model-select"), $("asset-model-other"));
  // Required fields, but "Other" is a real select value distinct from
  // blank — the browser's own required-attribute check on the <select>
  // can't see whether the paired text input was actually filled in, so
  // that combination needs its own check here.
  if (!manufacturer) {
    toast("Manufacturer is required.", "bad");
    return;
  }
  if (!model) {
    toast("Model is required.", "bad");
    return;
  }
  const editId = $("asset-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this asset?" : "Register this asset?"))) return;
  await withLoading($("asset-submit-btn"), editId ? "Saving…" : "Registering…", async () => {
    // asset_tag and supplier_id are deliberately absent from the update
    // body — AssetUpdateRequest doesn't accept either (asset_tag is
    // immutable, supplier_id doesn't change after intake).
    const purchaseCost = $("asset-purchase-cost").value;
    const currentValue = $("asset-current-value").value;
    const currency = $("asset-currency").value.trim();
    const result = editId
      ? await api(`/api/v1/assets/${editId}`, {
          method: "PUT",
          body: {
            manufacturer,
            model,
            serial_number: $("asset-serial-number").value || null,
            barcode_value: $("asset-barcode").value || null,
            purchase_cost: purchaseCost === "" ? null : Number(purchaseCost),
            current_value: currentValue === "" ? null : Number(currentValue),
            currency: currency || null,
          },
          auth: true,
        })
      : await api("/api/v1/assets", {
          method: "POST",
          body: {
            asset_tag: $("asset-tag").value,
            supplier_id: Number($("asset-supplier-id").value),
            manufacturer,
            model,
            serial_number: $("asset-serial-number").value || null,
            barcode_value: $("asset-barcode").value || null,
            purchase_cost: purchaseCost === "" ? null : Number(purchaseCost),
            current_value: currentValue === "" ? null : Number(currentValue),
            currency: currency || null,
          },
          auth: true,
        });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Asset updated." : "Asset registered.", "ok");
      $("form-asset").classList.add("hidden");
      resetAssetForm();
      reloadPage();
    }
  });
};

/* ---- Asset detail modal — Digital Twin facets (Tags/Attachments/
 * Timeline) that don't fit the plain list/edit form. See
 * NEXUS_ONE_ARCHITECTURE_PLAN §2.7 and app/services/asset_service.py. */
let currentAssetDetailId = null;

function openAssetDetail(a) {
  currentAssetDetailId = a.id;
  $("asset-detail-title").textContent = a.asset_tag;
  facts("asset-detail-facts", [
    ["Manufacturer / model", `${a.manufacturer} ${a.model}`, "tag"],
    ["Status", humanize(a.status), "activity"],
    ["Supplier", `#${a.supplier_id}`, "building"],
    ["Purchase cost", a.purchase_cost != null ? `${a.purchase_cost} ${a.currency || ""}`.trim() : null, "hash"],
    ["Current value", a.current_value != null ? `${a.current_value} ${a.currency || ""}`.trim() : null, "hash"],
  ]);
  $("asset-tag-input").value = "";
  $("asset-attachment-reference").value = "";
  $("asset-attachment-description").value = "";
  loadAssetDetailTags();
  loadAssetDetailAttachments();
  loadAssetDetailTimeline();
  $("asset-detail-modal").classList.remove("hidden");
}
$("asset-detail-close").onclick = () => $("asset-detail-modal").classList.add("hidden");
$("asset-detail-modal").onclick = (event) => {
  if (event.target === $("asset-detail-modal")) $("asset-detail-modal").classList.add("hidden");
};

async function loadAssetDetailTags() {
  const result = await api(`/api/v1/assets/${currentAssetDetailId}/tags`, { auth: true });
  const tags = result.status === 200 ? result.data.data : [];
  $("asset-detail-tags").innerHTML = tags
    .map(
      (t) => `<span class="tag-chip">${escapeHtml(t.tag)}<button type="button" data-remove-tag="${escapeHtml(t.tag)}" title="Remove tag">&times;</button></span>`
    )
    .join("");
  $("asset-detail-tags").querySelectorAll("[data-remove-tag]").forEach((btn) => {
    btn.onclick = async () => {
      const tag = btn.getAttribute("data-remove-tag");
      const result = await api(`/api/v1/assets/${currentAssetDetailId}/tags/${encodeURIComponent(tag)}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) loadAssetDetailTags();
    };
  });
}
$("form-asset-tag").onsubmit = async (event) => {
  event.preventDefault();
  const tag = $("asset-tag-input").value.trim();
  if (!tag) return;
  const result = await api(`/api/v1/assets/${currentAssetDetailId}/tags`, {
    method: "POST",
    body: { tag },
    auth: true,
  });
  if (result.status === 200 || result.status === 201) {
    $("asset-tag-input").value = "";
    loadAssetDetailTags();
  } else if (result.data.error_code === "ASSET_TAG_ALREADY_EXISTS") {
    toast("This asset already has that tag.", "bad");
  }
};

async function loadAssetDetailAttachments() {
  const result = await api(`/api/v1/assets/${currentAssetDetailId}/attachments`, { auth: true });
  const attachments = result.status === 200 ? result.data.data : [];
  $("asset-detail-attachments").innerHTML = attachments.length
    ? attachments
        .map(
          (att) => `<div class="attachment-row">
        <span>${icon(att.attachment_type === "photo" ? "view" : "edit")}<strong>${humanize(att.attachment_type)}</strong> &mdash; ${escapeHtml(att.reference)}${att.description ? ` <span style="color:var(--muted)">(${escapeHtml(att.description)})</span>` : ""}</span>
        <span style="color:var(--muted)">${fmt(att.created_at)}</span>
      </div>`
        )
        .join("")
    : `<p class="empty" style="padding:8px 0;">No attachments yet.</p>`;
}
$("form-asset-attachment").onsubmit = async (event) => {
  event.preventDefault();
  const reference = $("asset-attachment-reference").value.trim();
  if (!reference) {
    toast("A reference (URL or path) is required.", "bad");
    return;
  }
  const result = await api(`/api/v1/assets/${currentAssetDetailId}/attachments`, {
    method: "POST",
    body: {
      attachment_type: $("asset-attachment-type").value,
      reference,
      description: $("asset-attachment-description").value.trim() || null,
    },
    auth: true,
  });
  if (result.status === 200 || result.status === 201) {
    $("asset-attachment-reference").value = "";
    $("asset-attachment-description").value = "";
    loadAssetDetailAttachments();
  }
};

async function loadAssetDetailTimeline() {
  const result = await api(`/api/v1/assets/${currentAssetDetailId}/timeline`, { auth: true });
  const events = result.status === 200 ? result.data.data : [];
  $("asset-detail-timeline").innerHTML = events.length
    ? events
        .map(
          (e) => `<div class="timeline-row">
        <span class="timeline-when">${fmt(e.created_at)}</span>
        <span><code>${e.event_type}</code>${e.payload ? ` — ${escapeHtml(JSON.stringify(e.payload))}` : ""}</span>
      </div>`
        )
        .join("")
    : `<p class="empty" style="padding:8px 0;">No history yet.</p>`;
}

/* ---- Manufacturers / Models (master data feeding the Asset form's
 * Manufacturer/Model dropdowns) — structurally identical to Job Roles/
 * Departments above (see that section's comment), just counting assets
 * instead of employees. Two independent flat lists (Model is not a FK to
 * Manufacturer), so the two blocks below are near-duplicates of each
 * other rather than one filtering the other. ---- */
let manufacturersCache = [];

async function loadManufacturers() {
  $("manufacturers-table").innerHTML = skeletonTable();
  const includeInactive = $("manufacturers-include-inactive").checked;
  const result = await api(`/api/v1/manufacturers?limit=100&include_inactive=${includeInactive}`, { auth: true });
  if (result.status !== 200) return [];
  manufacturersCache = result.data.data.items || [];
  renderManufacturersTable(filterItems(manufacturersCache, $("manufacturers-search").value, ["name"]));
  // The Asset form's dropdown should only ever offer active
  // manufacturers, regardless of whether this page is currently showing
  // inactive ones too.
  populateMasterDataSelect(
    $("asset-manufacturer-select"),
    manufacturersCache.filter((m) => m.is_active)
  );
  return manufacturersCache;
}

$("manufacturers-search").oninput = () => {
  renderManufacturersTable(filterItems(manufacturersCache, $("manufacturers-search").value, ["name"]));
};
wireSearchSuggestions("manufacturers-search", "manufacturers-search-suggest", () => manufacturersCache, ["name"], (m) => m.name, (m) => (m.is_active ? "" : "inactive"));
wireCsvExport("btn-export-manufacturers", {
  headers: ["id", "name", "status", "assets"],
  getFilteredItems: () => filterItems(manufacturersCache, $("manufacturers-search").value, ["name"]),
  rowMapper: (m) => [m.id, m.name, m.is_active ? "Active" : "Inactive", m.asset_count ?? 0],
  filenamePrefix: "manufacturers",
});

$("manufacturers-include-inactive").onchange = loadManufacturers;

function renderManufacturersTable(items) {
  $("manufacturers-table").innerHTML = table(
    ["id", "name", "status", "assets", ""],
    items.length
      ? items
          .map(
            (m) => `<tr>
          <td>${m.id}</td>
          <td>${m.name}</td>
          <td><span class="status-pill ${m.is_active ? "good" : "bad"}">${m.is_active ? "Active" : "Inactive"}</span></td>
          <td>${m.asset_count ?? 0}</td>
          <td class="row-actions">
            <div class="row-actions-group">
              ${m.is_active ? `<button data-edit-manufacturer="${m.id}">${icon("edit")}Edit</button>` : ""}
              ${
                m.is_active
                  ? `<button class="danger" data-deactivate-manufacturer="${m.id}">${icon("deactivate")}Deactivate</button>`
                  : `<button data-reactivate-manufacturer="${m.id}">${icon("reactivate")}Reactivate</button>`
              }
            </div>
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No manufacturers match this search."
  );
  $("manufacturers-table").querySelectorAll("[data-edit-manufacturer]").forEach((btn) => {
    btn.onclick = () => {
      const m = items.find((x) => String(x.id) === btn.getAttribute("data-edit-manufacturer"));
      if (!m) return;
      $("manufacturer-edit-id").value = m.id;
      $("manufacturer-name").value = m.name;
      setButtonLabel($("manufacturer-submit-btn"), "check", "Save changes");
      $("form-manufacturer").classList.remove("hidden");
      $("form-manufacturer").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  $("manufacturers-table").querySelectorAll("[data-deactivate-manufacturer]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Deactivate this manufacturer?"))) return;
      const result = await api(`/api/v1/manufacturers/${btn.getAttribute("data-deactivate-manufacturer")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Manufacturer deactivated.", "ok");
        reloadPage();
      }
    };
  });
  $("manufacturers-table").querySelectorAll("[data-reactivate-manufacturer]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Reactivate this manufacturer?"))) return;
      const result = await api(`/api/v1/manufacturers/${btn.getAttribute("data-reactivate-manufacturer")}/reactivate`, {
        method: "PATCH",
        auth: true,
      });
      if (result.status === 200) {
        toast("Manufacturer reactivated.", "ok");
        reloadPage();
      }
    };
  });
}

function resetManufacturerForm() {
  $("form-manufacturer").reset();
  $("manufacturer-edit-id").value = "";
  setButtonLabel($("manufacturer-submit-btn"), "plus", "Create manufacturer");
}

$("btn-new-manufacturer").onclick = () => {
  resetManufacturerForm();
  $("form-manufacturer").classList.remove("hidden");
};
$("manufacturer-cancel-btn").onclick = () => {
  $("form-manufacturer").classList.add("hidden");
  resetManufacturerForm();
};
$("form-manufacturer").onsubmit = async (event) => {
  event.preventDefault();
  const editId = $("manufacturer-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this manufacturer?" : "Create this manufacturer?"))) return;
  await withLoading($("manufacturer-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const result = await api(editId ? `/api/v1/manufacturers/${editId}` : "/api/v1/manufacturers", {
      method: editId ? "PUT" : "POST",
      body: { name: $("manufacturer-name").value },
      auth: true,
    });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Manufacturer updated." : "Manufacturer created.", "ok");
      $("form-manufacturer").classList.add("hidden");
      resetManufacturerForm();
      reloadPage();
    }
  });
};

let assetModelsCache = [];

async function loadAssetModels() {
  $("asset-models-table").innerHTML = skeletonTable();
  const includeInactive = $("asset-models-include-inactive").checked;
  const result = await api(`/api/v1/asset-models?limit=100&include_inactive=${includeInactive}`, { auth: true });
  if (result.status !== 200) return [];
  assetModelsCache = result.data.data.items || [];
  renderAssetModelsTable(filterItems(assetModelsCache, $("asset-models-search").value, ["name"]));
  // Same "dropdown only shows active items" rule as Manufacturer above.
  populateMasterDataSelect(
    $("asset-model-select"),
    assetModelsCache.filter((m) => m.is_active)
  );
  return assetModelsCache;
}

$("asset-models-search").oninput = () => {
  renderAssetModelsTable(filterItems(assetModelsCache, $("asset-models-search").value, ["name"]));
};
wireSearchSuggestions("asset-models-search", "asset-models-search-suggest", () => assetModelsCache, ["name"], (m) => m.name, (m) => (m.is_active ? "" : "inactive"));
wireCsvExport("btn-export-asset-models", {
  headers: ["id", "name", "status", "assets"],
  getFilteredItems: () => filterItems(assetModelsCache, $("asset-models-search").value, ["name"]),
  rowMapper: (m) => [m.id, m.name, m.is_active ? "Active" : "Inactive", m.asset_count ?? 0],
  filenamePrefix: "models",
});

$("asset-models-include-inactive").onchange = loadAssetModels;

function renderAssetModelsTable(items) {
  $("asset-models-table").innerHTML = table(
    ["id", "name", "status", "assets", ""],
    items.length
      ? items
          .map(
            (m) => `<tr>
          <td>${m.id}</td>
          <td>${m.name}</td>
          <td><span class="status-pill ${m.is_active ? "good" : "bad"}">${m.is_active ? "Active" : "Inactive"}</span></td>
          <td>${m.asset_count ?? 0}</td>
          <td class="row-actions">
            <div class="row-actions-group">
              ${m.is_active ? `<button data-edit-asset-model="${m.id}">${icon("edit")}Edit</button>` : ""}
              ${
                m.is_active
                  ? `<button class="danger" data-deactivate-asset-model="${m.id}">${icon("deactivate")}Deactivate</button>`
                  : `<button data-reactivate-asset-model="${m.id}">${icon("reactivate")}Reactivate</button>`
              }
            </div>
          </td>
        </tr>`
          )
          .join("")
      : null,
    "No models match this search."
  );
  $("asset-models-table").querySelectorAll("[data-edit-asset-model]").forEach((btn) => {
    btn.onclick = () => {
      const m = items.find((x) => String(x.id) === btn.getAttribute("data-edit-asset-model"));
      if (!m) return;
      $("asset-model-edit-id").value = m.id;
      $("asset-model-name").value = m.name;
      setButtonLabel($("asset-model-submit-btn"), "check", "Save changes");
      $("form-asset-model").classList.remove("hidden");
      $("form-asset-model").scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  $("asset-models-table").querySelectorAll("[data-deactivate-asset-model]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Deactivate this model?"))) return;
      const result = await api(`/api/v1/asset-models/${btn.getAttribute("data-deactivate-asset-model")}`, {
        method: "DELETE",
        auth: true,
      });
      if (result.status === 200) {
        toast("Model deactivated.", "ok");
        reloadPage();
      }
    };
  });
  $("asset-models-table").querySelectorAll("[data-reactivate-asset-model]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmModal("Reactivate this model?"))) return;
      const result = await api(`/api/v1/asset-models/${btn.getAttribute("data-reactivate-asset-model")}/reactivate`, {
        method: "PATCH",
        auth: true,
      });
      if (result.status === 200) {
        toast("Model reactivated.", "ok");
        reloadPage();
      }
    };
  });
}

function resetAssetModelForm() {
  $("form-asset-model").reset();
  $("asset-model-edit-id").value = "";
  setButtonLabel($("asset-model-submit-btn"), "plus", "Create model");
}

$("btn-new-asset-model").onclick = () => {
  resetAssetModelForm();
  $("form-asset-model").classList.remove("hidden");
};
$("asset-model-cancel-btn").onclick = () => {
  $("form-asset-model").classList.add("hidden");
  resetAssetModelForm();
};
$("form-asset-model").onsubmit = async (event) => {
  event.preventDefault();
  const editId = $("asset-model-edit-id").value;
  if (!(await confirmModal(editId ? "Save changes to this model?" : "Create this model?"))) return;
  await withLoading($("asset-model-submit-btn"), editId ? "Saving…" : "Creating…", async () => {
    const result = await api(editId ? `/api/v1/asset-models/${editId}` : "/api/v1/asset-models", {
      method: editId ? "PUT" : "POST",
      body: { name: $("asset-model-name").value },
      auth: true,
    });
    if (result.status === 200 || result.status === 201) {
      toast(editId ? "Model updated." : "Model created.", "ok");
      $("form-asset-model").classList.add("hidden");
      resetAssetModelForm();
      reloadPage();
    }
  });
};

/* ---- Audit log (read-only) ---- */
let auditLogsCache = [];

async function loadAuditLogs() {
  $("audit-table").innerHTML = skeletonTable();
  const params = new URLSearchParams({ limit: "50" });
  const resourceType = $("audit-resource-type").value;
  const action = $("audit-action").value;
  const resourceId = $("audit-resource-id").value.trim();
  const userId = $("audit-user-id").value.trim();
  if (resourceType) params.set("resource_type", resourceType);
  if (action) params.set("action", action);
  if (resourceId) params.set("resource_id", resourceId);
  if (userId) params.set("user_id", userId);
  const result = await api(`/api/v1/audit-logs?${params.toString()}`, { auth: true });
  if (result.status !== 200) {
    $("audit-table").innerHTML = `<p class="empty">Could not load audit log (${result.data.error_code || result.status}).</p>`;
    return;
  }
  auditLogsCache = result.data.data.items || [];
  renderAuditTable(auditLogsCache);
}

function renderAuditTable(items) {
  $("audit-table").innerHTML = table(
    ["id", "when", "user_id", "action", "resource", "old_value", "new_value"],
    items.length
      ? items
          .map(
            (row) => `<tr>
          <td>${row.id}</td>
          <td>${fmt(row.created_at)}</td>
          <td>${fmt(row.user_id)}</td>
          <td>${humanize(row.action)}</td>
          <td>${humanize(row.resource_type)}${row.resource_id ? ` #${row.resource_id}` : ""}</td>
          <td><code>${row.old_value ? escapeHtml(JSON.stringify(row.old_value)) : "—"}</code></td>
          <td><code>${row.new_value ? escapeHtml(JSON.stringify(row.new_value)) : "—"}</code></td>
        </tr>`
          )
          .join("")
      : null,
    "No audit records match this filter."
  );
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

$("btn-toggle-audit-filters").onclick = () => {
  const panel = $("audit-filter-panel");
  // classList.toggle() returns the class's new presence — true means
  // "hidden" is now on the element, i.e. the panel just became hidden.
  const nowHidden = panel.classList.toggle("hidden");
  $("btn-toggle-audit-filters").setAttribute("aria-expanded", String(!nowHidden));
};

$("btn-audit-search").onclick = loadAuditLogs;
$("btn-audit-clear").onclick = () => {
  $("audit-resource-type").value = "";
  $("audit-action").value = "";
  $("audit-resource-id").value = "";
  $("audit-user-id").value = "";
  loadAuditLogs();
};
// No client-side search box on this page (filtering happens server-side
// via the Search button above) — exports exactly whatever the last
// search/Clear filters click loaded, same rows currently on screen.
wireCsvExport("btn-export-audit", {
  headers: ["id", "when", "user_id", "action", "resource", "old_value", "new_value"],
  getFilteredItems: () => auditLogsCache,
  rowMapper: (row) => [
    row.id,
    fmt(row.created_at),
    row.user_id ?? "",
    humanize(row.action),
    `${humanize(row.resource_type)}${row.resource_id ? ` #${row.resource_id}` : ""}`,
    row.old_value ? JSON.stringify(row.old_value) : "",
    row.new_value ? JSON.stringify(row.new_value) : "",
  ],
  filenamePrefix: "audit-log",
});

/* ---- Events (Foundation Core Phase 2: event emission infrastructure) ----
 * Every event mirrors an audit row 1:1 — see publish_event() in
 * app/services/event_service.py, called from inside record_audit_event
 * itself. This page is read-only, same shape as the Audit log page above. */
let eventsCache = [];

async function loadEvents() {
  $("events-table").innerHTML = skeletonTable();
  const params = new URLSearchParams({ limit: "50" });
  const resourceType = $("event-resource-type").value;
  const eventType = $("event-type-filter").value.trim();
  const resourceId = $("event-resource-id").value.trim();
  const companyId = $("event-company-id").value.trim();
  if (resourceType) params.set("resource_type", resourceType);
  if (eventType) params.set("event_type", eventType);
  if (resourceId) params.set("resource_id", resourceId);
  if (companyId) params.set("company_id", companyId);
  const result = await api(`/api/v1/events?${params.toString()}`, { auth: true });
  if (result.status !== 200) {
    $("events-table").innerHTML = `<p class="empty">Could not load events (${result.data.error_code || result.status}).</p>`;
    return;
  }
  eventsCache = result.data.data.items || [];
  renderEventsTable(eventsCache);
}

function renderEventsTable(items) {
  $("events-table").innerHTML = table(
    ["id", "when", "event_type", "resource", "company_id", "payload"],
    items.length
      ? items
          .map(
            (row) => `<tr>
          <td>${row.id}</td>
          <td>${fmt(row.created_at)}</td>
          <td><code>${row.event_type}</code></td>
          <td>${humanize(row.resource_type)}${row.resource_id ? ` #${row.resource_id}` : ""}</td>
          <td>${fmt(row.company_id)}</td>
          <td><code>${row.payload ? escapeHtml(JSON.stringify(row.payload)) : "—"}</code></td>
        </tr>`
          )
          .join("")
      : null,
    "No events match this filter."
  );
}

$("btn-toggle-event-filters").onclick = () => {
  const panel = $("event-filter-panel");
  const nowHidden = panel.classList.toggle("hidden");
  $("btn-toggle-event-filters").setAttribute("aria-expanded", String(!nowHidden));
};

$("btn-event-search").onclick = loadEvents;
$("btn-event-clear").onclick = () => {
  $("event-resource-type").value = "";
  $("event-type-filter").value = "";
  $("event-resource-id").value = "";
  $("event-company-id").value = "";
  loadEvents();
};
wireCsvExport("btn-export-events", {
  headers: ["id", "when", "event_type", "resource", "company_id", "payload"],
  getFilteredItems: () => eventsCache,
  rowMapper: (row) => [
    row.id,
    fmt(row.created_at),
    row.event_type,
    `${humanize(row.resource_type)}${row.resource_id ? ` #${row.resource_id}` : ""}`,
    fmt(row.company_id),
    row.payload ? JSON.stringify(row.payload) : "",
  ],
  filenamePrefix: "events",
});

function clearSession() {
  state.accessToken = null;
  state.refreshToken = null;
  state.user = null;
  clearPersistedSession();
  showGate();
  // Reset sidebar back to Overview and clear the URL hash so the next
  // login (possibly a different user/role) doesn't land on whatever
  // section this session happened to be viewing.
  activateSection("section-overview", { updateHash: false });
  history.replaceState(null, "", location.pathname + location.search);
}

$("nav-signin").onclick = () => {
  $("auth-card").scrollIntoView({ behavior: "smooth", block: "center" });
};

$("tab-login").onclick = () => {
  $("tab-login").classList.add("on");
  $("tab-register").classList.remove("on");
  $("form-login").classList.remove("hidden");
  $("form-register").classList.add("hidden");
};

$("tab-register").onclick = () => {
  $("tab-register").classList.add("on");
  $("tab-login").classList.remove("on");
  $("form-register").classList.remove("hidden");
  $("form-login").classList.add("hidden");
};

$("form-login").onsubmit = async (event) => {
  event.preventDefault();
  const button = event.submitter || $("form-login").querySelector("button[type=submit]");
  await withLoading(button, "Logging in…", async () => {
    const result = await api("/api/v1/auth/login", {
      method: "POST",
      body: {
        email: $("login-email").value,
        password: $("login-password").value,
      },
    });
    if (result.status === 200) {
      state.accessToken = result.data.data.access_token;
      state.refreshToken = result.data.data.refresh_token;
      toast("Login succeeded. Access token and refresh token issued.", "ok");
      await loadMe();
    }
  });
};

$("form-register").onsubmit = async (event) => {
  event.preventDefault();
  const button = event.submitter || $("form-register").querySelector("button[type=submit]");
  await withLoading(button, "Creating account…", async () => {
    const result = await api("/api/v1/auth/register", {
      method: "POST",
      body: {
        email: $("reg-email").value,
        password: $("reg-password").value,
        full_name: $("reg-name").value || null,
      },
    });
    if (result.status === 201) {
      $("login-email").value = $("reg-email").value;
      $("login-password").value = $("reg-password").value;
      toast("Account created. Use Login.", "ok");
      $("tab-login").click();
    }
  });
};

$("btn-refresh").onclick = async () => {
  if (!state.refreshToken) {
    toast("Refresh token missing. Login again.", "bad");
    return;
  }
  await withLoading($("btn-refresh"), "Refreshing…", async () => {
    const result = await api("/api/v1/auth/refresh", {
      method: "POST",
      body: { refresh_token: state.refreshToken },
    });
    if (result.status === 200) {
      state.accessToken = result.data.data.access_token;
      state.refreshToken = result.data.data.refresh_token;
      toast("New access token issued. Session rotated.", "ok");
      await loadMe();
    }
  });
};

$("btn-logout").onclick = async () => {
  if (!(await confirmModal("Log out?"))) return;
  await withLoading($("btn-logout"), "Logging out…", async () => {
    const result = await api("/api/v1/auth/logout", { method: "POST", body: {}, auth: true });
    if (result.status === 200 || result.status === 401) {
      toast("Logged out. Access token jti revoked.", "ok");
      clearSession();
    }
  });
};

$("btn-logout-all").onclick = async () => {
  if (!(await confirmModal("Log out of all sessions?"))) return;
  await withLoading($("btn-logout-all"), "Revoking…", async () => {
    const result = await api("/api/v1/auth/logout-all", { method: "POST", auth: true });
    if (result.status === 200) {
      toast("All sessions revoked.", "ok");
      clearSession();
    }
  });
};

// Runs on every real page load, including the ones reloadPage() fires
// after a create/update/delete. A plain location.reload() re-fetches /ui
// and re-runs this whole script from scratch — a real, visible full
// reload, not an in-place update. The URL hash (#employees, #companies,
// ...) already tells us which page to reopen; this just has to sign the
// session back in and restore that page's filters/search before the user
// notices.
(async function restoreSession() {
  const saved = sessionStorage.getItem(SESSION_STORAGE_KEY);
  // Nothing persisted — the top-of-file check already hid #restore-curtain
  // in this exact case (same sessionStorage read), so #gate is already
  // showing normally. Nothing left to do here.
  if (!saved) return;
  let parsed;
  try {
    parsed = JSON.parse(saved);
  } catch {
    // Bad data under a key that WAS present, so the curtain is still up
    // (the top-of-file check only looks at "does the key exist", not
    // whether it parses) — this path must explicitly reveal #gate via
    // showGate(), or the curtain stays up forever with nothing under it.
    clearPersistedSession();
    showGate();
    return;
  }
  if (!parsed.accessToken) {
    showGate();
    return;
  }
  state.accessToken = parsed.accessToken;
  state.refreshToken = parsed.refreshToken;
  showPageLoading();

  try {
    // Switch to the page the URL hash points to BEFORE loadMe() runs —
    // loadMe() -> loadAdmin() is several sequential requests (companies,
    // employees, suppliers, assets, audit logs, sessions), and Overview
    // is whatever the static HTML shows by default, so waiting until all
    // of that finishes to switch pages would show Overview for that
    // whole stretch before jumping to Companies/Suppliers/etc. Switching
    // first means the correct page is already showing (just still
    // filling in) the moment loadMe() reveals the app.
    const wanted = currentHashSection();
    if (wanted !== "section-overview") activateSection(wanted, { updateHash: false });

    const ok = await loadMe();
    if (ok) {
    // loadMe() -> loadAdmin() just loaded every list with default filters
    // (e.g. the Employees company filter defaulting to the first
    // company) — re-apply whatever filters/search were actually in use
    // before the reload, so the page doesn't quietly snap back to a
    // default view.
    const pageState = readPageState();
    if (pageState.usersSearch) {
      $("users-search").value = pageState.usersSearch;
      $("users-search").dispatchEvent(new Event("input"));
    }
    if (pageState.companiesSearch) $("companies-search").value = pageState.companiesSearch;
    if (pageState.companiesSort) $("companies-sort").value = pageState.companiesSort;
    if (pageState.companiesTypeFilter) $("companies-type-filter").value = pageState.companiesTypeFilter;
    if (pageState.companiesSort || pageState.companiesTypeFilter) {
      await loadCompanies();
    } else if (pageState.companiesSearch) {
      $("companies-search").dispatchEvent(new Event("input"));
    }
    if (pageState.sessionsSearch) {
      $("sessions-search").value = pageState.sessionsSearch;
      $("sessions-search").dispatchEvent(new Event("input"));
    }
    if (pageState.employeesSearch) $("employees-search").value = pageState.employeesSearch;
    // "Include exited" now defaults to checked in the HTML itself (so
    // exited employees aren't hidden by default) — only override that
    // default when a previous reload actually saved an explicit value,
    // so unchecking it and reloading is remembered instead of always
    // reverting to checked.
    if ("employeeIncludeExited" in pageState) {
      $("employee-include-exited").checked = !!pageState.employeeIncludeExited;
    }
    if (
      pageState.employeeCompanyFilter ||
      "employeeIncludeExited" in pageState ||
      pageState.employeeDepartmentFilter
    ) {
      if (pageState.employeeCompanyFilter) {
        $("employee-company-filter").value = pageState.employeeCompanyFilter;
        employeeCompanyFilterCombo.refresh();
      }
      if (pageState.employeeDepartmentFilter) $("employee-department-filter").value = pageState.employeeDepartmentFilter;
      await loadEmployees();
    } else if (pageState.employeesSearch) {
      $("employees-search").dispatchEvent(new Event("input"));
    }
    if (pageState.suppliersSearch) $("suppliers-search").value = pageState.suppliersSearch;
    if (pageState.supplierStatusFilter) {
      $("supplier-status-filter").value = pageState.supplierStatusFilter;
      await loadSuppliers();
    } else if (pageState.suppliersSearch) {
      $("suppliers-search").dispatchEvent(new Event("input"));
    }
    if (pageState.assetsSearch) $("assets-search").value = pageState.assetsSearch;
    if (pageState.assetStatusFilter) {
      $("asset-status-filter").value = pageState.assetStatusFilter;
      await loadAssets();
    } else if (pageState.assetsSearch) {
      $("assets-search").dispatchEvent(new Event("input"));
    }
    // Same reasoning as employeeIncludeExited above.
    if ("departmentsIncludeInactive" in pageState) {
      $("departments-include-inactive").checked = !!pageState.departmentsIncludeInactive;
    }
    if ("departmentsIncludeInactive" in pageState || pageState.departmentsParentFilter) {
      if (pageState.departmentsParentFilter) {
        // The parent filter's non-"top-level" options are department
        // names loaded from the API (populateDepartmentsParentFilter), so
        // setting .value to a saved department id can't stick until after
        // a load has populated them — hence the extra round-trip here.
        await loadDepartments();
        $("departments-parent-filter").value = pageState.departmentsParentFilter;
      }
      await loadDepartments();
    }
    if (pageState.departmentsSearch) {
      $("departments-search").value = pageState.departmentsSearch;
      $("departments-search").dispatchEvent(new Event("input"));
    }
    // Same reasoning as employeeIncludeExited above.
    if ("jobRolesIncludeInactive" in pageState) {
      $("job-roles-include-inactive").checked = !!pageState.jobRolesIncludeInactive;
      await loadJobRoles();
    }
    if (pageState.jobRolesSearch) {
      $("job-roles-search").value = pageState.jobRolesSearch;
      $("job-roles-search").dispatchEvent(new Event("input"));
    }
    // Same reasoning as employeeIncludeExited above.
    if ("applicationsIncludeInactive" in pageState) {
      $("applications-include-inactive").checked = !!pageState.applicationsIncludeInactive;
      await loadApplications();
    }
    if (pageState.applicationsSearch) {
      $("applications-search").value = pageState.applicationsSearch;
      $("applications-search").dispatchEvent(new Event("input"));
    }
    // Same reasoning as employeeIncludeExited above.
    if ("manufacturersIncludeInactive" in pageState) {
      $("manufacturers-include-inactive").checked = !!pageState.manufacturersIncludeInactive;
      await loadManufacturers();
    }
    if (pageState.manufacturersSearch) {
      $("manufacturers-search").value = pageState.manufacturersSearch;
      $("manufacturers-search").dispatchEvent(new Event("input"));
    }
    // Same reasoning as employeeIncludeExited above.
    if ("assetModelsIncludeInactive" in pageState) {
      $("asset-models-include-inactive").checked = !!pageState.assetModelsIncludeInactive;
      await loadAssetModels();
    }
    if (pageState.assetModelsSearch) {
      $("asset-models-search").value = pageState.assetModelsSearch;
      $("asset-models-search").dispatchEvent(new Event("input"));
    }

    // Now that the role is actually known, re-validate the optimistic
    // switch from earlier: fall back to Overview only if this page turns
    // out not to be accessible after all (e.g. the user just demoted
    // their own role away from admin) — otherwise leave it exactly where
    // it is.
    const navItem = document.querySelector(`.nav-item[data-section="${wanted}"]`);
    const stillAccessible = navItem && !navItem.classList.contains("hidden");
    if (!stillAccessible) activateSection("section-overview");
    }
  } catch {
    // A genuinely failed request (e.g. the API unreachable) throws
    // instead of resolving to a handled {status, data} result — without
    // this, #restore-curtain would stay up forever with nothing under
    // it, instead of falling back to the login form like it always used to.
    showGate();
  } finally {
    hidePageLoading();
  }
})();
