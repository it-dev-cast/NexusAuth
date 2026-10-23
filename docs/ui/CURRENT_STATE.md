# nexusAuth Frontend — What Actually Exists

> This is the accurate counterpart to the other files in this folder. Everything else in `docs/ui/` describes a separate, much larger React codebase (`NexusOne-CoreFoundation`) that this repository is not part of. This document describes `frontend/` as it is really built, today, in this repo.
>
> Last verified against the live code: 2026-09-06. If you find this drifting from the real CSS/HTML/JS again, fix this file rather than trusting it blindly — it has gone stale before (see git history: it once described a single-theme, purple-accent version of the app that predated the theme picker below by a wide margin).

## Stack

Plain HTML/CSS/JS. No framework, no build step, no npm dependencies.

- [`frontend/index.html`](../../frontend/index.html) — all markup, both the pre-login marketing page and the post-login dashboard, in one file. FastAPI serves it at `GET /ui` (see `main.py`) and serves `/static/*` from this same `frontend/` directory via `StaticFiles`.
- [`frontend/styles.css`](../../frontend/styles.css) — all styling. One stylesheet, no preprocessor, no CSS modules.
- [`frontend/app.js`](../../frontend/app.js) — all behavior. One script, no bundler, talks to the API with plain `fetch`.
- [`frontend/branding/`](../../frontend/branding/) — the real Casterly logo assets (cropped from the actual brand file, not hand-drawn): `casterly-logo-horizontal.png` (icon + wordmark, nav bars), `casterly-mark.png` (icon + wordmark, white-backed, sidebar), `casterly-icon.png` / `casterly-icon-white.png` (icon-only, navy-backed / white-backed), `favicon.ico`.

## Theme system

There **is** a theme picker — nine named themes, a palette-icon trigger (top-right of every page, next to the page heading) that opens a dropdown listing each theme's swatch dot + name, with a checkmark on the active one. Choice persists in `localStorage` (`THEME_STORAGE_KEY` in `app.js`) and defaults to the OS's light/dark preference on first visit.

| Theme ID | Label | Family |
|---|---|---|
| `casterly-light` | Casterly Light | Light (default) |
| `executive-white` | Executive White | Light |
| `ocean-blue` | Ocean Blue | Light |
| `slate-professional` | Slate Professional | Light |
| `emerald` | Emerald | Light |
| `purple-enterprise` | Purple Enterprise | Light |
| `casterly-erp-green` | Casterly ERP Green | Light |
| `graphite-dark` | Graphite Dark | Dark |
| `midnight-blue` | Midnight Blue | Dark |

Implementation: `applyTheme()`/`THEMES`/`renderThemeSwatchPanel()` in `app.js` set `document.documentElement.dataset.theme`, which every `:root[data-theme="..."]` block in `styles.css` (interactive tokens only — see below) reacts to.

## Color tokens

Defined as CSS custom properties at the top of `styles.css`, split into three groups:

- **Fixed brand identity** (`--dark`, `--dark-2`, `--lime`) — never changes with the theme picker. `--dark: #1a0a37` is the exact pixel value baked into the logo PNG crops.
- **Fixed semantic tokens** (`--color-success`/`--color-success-bg`, `--color-warning`/`--color-warning-bg`, `--danger`/`--color-danger-bg`/`--color-danger-border`) — status meaning must read the same regardless of the selected theme, so these are never overridden per-theme either.
- **Interactive theme tokens** (`--accent`, `--accent-h`, `--accent2`, `--ink`, `--muted`, `--line`, `--bg`, `--card`, `--sidebar-*`) — the ones each `:root[data-theme="..."]` block actually overrides.

Default (Casterly Light) values:

| Token | Value | Used for |
|---|---|---|
| `--ink` | `#1d301d` | body text |
| `--muted` | `#6b6480` | secondary text |
| `--line` | `#e2e5dc` | borders |
| `--bg` | `#f9faf9` | page/content background |
| `--card` | `#ffffff` | card surfaces |
| `--accent` | `#678b27` | primary actions, active nav, focus ring |
| `--accent-h` | `#55701f` | primary action hover |
| `--accent2` | `#06b6d4` | secondary/info button family |
| `--lime` | `#c3d62e` | fixed brand accent — admin badge, marketing CTA |
| `--danger` | `#b42318` | destructive text/icon color (fixed across themes) |
| `--color-danger-bg` | `#fef3f2` | destructive button/pill background (fixed across themes) |
| `--dark` | `#1a0a37` | nav bars, sidebar-brand chrome, hero, footer |

`--secondary`/`--secondary-bg` are *derived* (via `color-mix()` from `--accent`/`--ink`/`--card`), not per-theme literals — every theme gets a correctly-tinted secondary surface for free.

## Icon system

Every action button, form-field label, fact list (Current user/JWT claims/Department detail), and table header uses an inline SVG icon — no icon font/library.

- `ICONS` (object in `app.js`) is the single source of truth for path data — one entry per action verb or field concept (`edit`, `delete`, `deactivate`, `reactivate`, `check`, `mail`, `building`, `download`, etc.).
- `icon(name)` wraps a path in `<svg class="btn-icon">` for buttons; `factIcon(name)` wraps it in `<svg class="fact-icon">` for fact-list/table-header labels.
- Static markup in `index.html` (sidebar nav, form field labels, the small set of buttons not rendered by JS) inlines the same path data literally, with a comment noting `ICONS` in `app.js` as the canonical copy to keep in sync.
- Sizing lives in `.btn-icon`/`.field-icon`/`.fact-icon` in `styles.css`, not on individual `<svg>` tags.

## Page structure

Two top-level states inside one HTML document, toggled by JS (`showGate()` / `showApp()` in `app.js`), never separate page loads:

### 1. Pre-login: `#gate` — landing + auth card

- `.site-nav` — sticky dark nav: logo, a "Sign in" button that smooth-scrolls to the auth card.
- `.hero` — dark gradient section, headline + bullet points on the left, the login/register card (`#auth-card`) docked on the right.

### 2. Post-login: `#app` — a sidebar dashboard, not stacked tabs

- `.sidebar` — dark sidebar (collapsible to icons-only, persisted in `localStorage`): logo, icon+label nav buttons (`.nav-item`), user identity + role badge + Logout pinned at the bottom.
- `.content` — shows exactly one `.page-section` at a time; clicking a `.nav-item` hides all other sections and shows the matching one. Browser Back/Forward works via `location.hash` + a `hashchange` listener (`HASH_TO_SECTION`/`currentHashSection()`/`activateSection()`).
- Sections, gated by role (`.admin-only` class, toggled in `loadMe()`):
  - **Overview** — always visible. Welcome heading, current-user facts, JWT claims, refresh/logout-all buttons. The 5-tile KPI strip (Registered users / Successful logins / Active sessions / Failed attempts / Locked accounts) and the Recent Activity feed inside it are admin-only.
  - **Users / Companies / Employees / Departments / Job Roles / Applications / Suppliers / Assets / Manufacturers / Models / Audit log / Events** — admin-only. Events is read-only (Foundation Core Phase 2's event-emission stream — see `app/services/event_service.py`), same shape as Audit log.
  - **Sessions** — always visible, everyone's own sessions.
  - Every list page has an **Export** button (`wireCsvExport()` in `app.js`) that downloads whatever's currently filtered on screen as a `.csv`.

Same caveat as before still applies: **only nav buttons and the KPI strip carry `.admin-only`** — the admin `.page-section` elements do not, because they already share the `.hidden` class with the nav-switching logic. Don't add `.admin-only` back onto a `.page-section`.

## Component patterns actually in use

Real reusable patterns (plain CSS classes, not components) — reach for them before inventing new markup:

| Class | What it is |
|---|---|
| `.card` | White/theme-surface rounded panel, `--shadow-sm` |
| `.card-head` | Flex row: heading + search + action button(s) (New/Export), used at the top of every resource card |
| `.entity-form` | The collapsible create/edit form pattern — `.form-grid` for the 2-column field layout, hidden by default, toggled by a "+ New X" button. Every field label carries a `.field-icon` |
| `.status-pill` | Small, fully-rounded status badge; `.good`/`.bad` modifiers use the fixed semantic success/danger tokens |
| `.badge` | Role badge; `.role-admin` gives it the fixed lime/dark brand pair |
| `.row-actions` | Compact inline button/select group inside a table cell (status transition dropdown + Apply, per-row Edit/Delete). `.reserved` (`visibility: hidden`, not removed) keeps a terminal row's dead controls taking up the same space as an active row's, so trailing columns stay aligned |
| `.hint` | Small muted helper text under a section heading |
| `table` / `th, td` | Plain HTML tables built by the `table()` helper in `app.js`. `white-space: nowrap` on every cell keeps row heights uniform — a long value scrolls horizontally (`.table-scroll`) instead of wrapping and stretching just that row |
| select + "Other (type below)…" | The pattern for a master-data-backed field that must also accept a free-text value not yet in the list (Employee Job role/Department, Supplier Category/Terms, Asset Manufacturer/Model) — `setSelectOrOther()`/`getSelectOrOther()` in `app.js` |
| `.tag-chip` / `.chip-row` | Removable pill (name + × button) for a per-record free-form tag list — currently only Asset's detail modal |
| `.inline-form` | A compact one-line add-form (input(s) + a small submit button) inside a modal — used for "add a tag" / "add an attachment" in Asset detail |

## Master-data modules

Department, Job Role, Application, Manufacturer, and Model are all the same shape: a global (not company-scoped), admin-managed, soft-deletable (`is_active`) list with its own page (search, Include inactive, New/Edit/Deactivate/Reactivate, a usage-count column) and its own dropdown elsewhere in the app. Copy the nearest existing one (Job Role is the simplest template) rather than inventing a new pattern.

## Asset detail modal (Digital Twin facets)

`#asset-detail-modal`, opened via each row's new "View" button on the Assets page — read-mostly, mirrors the Department detail modal's `.modal-card.wide` pattern but with more content, so it scrolls (`max-height: 80vh; overflow-y: auto`, already on `.modal-card.wide`). Shows:
- **Facts** (`#asset-detail-facts`) — manufacturer/model, status, supplier, and the Financials facet (purchase cost / current value, both nullable, plus an ISO-4217 currency code) — also editable on the main Asset form itself.
- **Tags** (`#asset-detail-tags`) — free-form per-asset labels, add/remove inline; also folded into the Assets page's search (`GET /api/v1/assets?search=`).
- **Attachments** (`#asset-detail-attachments`) — a reference (URL/path) + type (document/photo/other) + optional description; no file upload/storage exists in this build, so this is a link/description only.
- **Timeline** (`#asset-detail-timeline`) — not its own data; reads `GET /api/v1/assets/{id}/timeline`, which derives history from the `events` table (Foundation Core Phase 2's event-emission stream) rather than a duplicate history table.

Backing endpoints: `GET/POST /api/v1/assets/{id}/tags`, `DELETE /api/v1/assets/{id}/tags/{tag}`, `GET/POST /api/v1/assets/{id}/attachments`, `GET /api/v1/assets/{id}/timeline` — same read/write roles as the parent Asset resource, no separate permission entry.

**A `fmt()` bug this surfaced and fixed**: `fmt()` used to decide "is this a date?" purely by `String(value).length > 8`, so a plain string like "Dell Latitude 5420" silently got misparsed as a date ("Jan 1, 5420" — JS's loose `Date` parser read "5420" as a year). `fmt()` now only attempts date parsing when the value actually looks like an ISO 8601 timestamp (`^\d{4}-\d{2}-\d{2}`) — the only shape any real date value in this app is ever serialized as. Worth remembering if a future `facts()`/`fmt()` call renders a plain string that happens to contain a 4-digit number.

## What this means for future work

- **Reuse these classes and the existing `api()` helper in `app.js`** before adding new CSS or a new fetch pattern.
- There is no build step: edit `frontend/*` directly and refresh — FastAPI serves it live via `StaticFiles`, no restart needed for HTML/CSS/JS changes (only `main.py`/`app/*` changes need a server restart).
- Semantic status colors (`--color-success*`, `--color-warning*`, `--danger`/`--color-danger*`) are fixed across every theme by design (§7 of `DESIGN_SYSTEM.md`, the one section of that React-oriented doc whose literal values genuinely were carried over here) — don't add a per-theme override for one of these tokens without a deliberate reason.
- If nexusAuth is ever merged into the real `NexusOne-CoreFoundation` platform described in the other files in this folder, this page becomes the migration starting point, not something to delete outright — it's the accurate record of what existed before the merge.
