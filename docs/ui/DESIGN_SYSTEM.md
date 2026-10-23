> ⚠️ **Reference only — does not describe this repository.** This document is a snapshot from a separate, larger codebase (`NexusOne-CoreFoundation`, React + `frontend/src/...`, multi-theme design system). **nexusAuth has none of that** — its real frontend is plain HTML/CSS/JS under `frontend/` (see [CURRENT_STATE.md](CURRENT_STATE.md) for what actually exists). Kept here for reference in case nexusAuth is ever folded into that larger platform.

---

# NEXUS One Design System

## 1. Purpose

This document defines the **canonical visual and interaction language** for NEXUS One. It is grounded in the design system already implemented in the current CoreFoundation frontend.

The goal is not to make every page visually identical. The goal is to make every page feel like part of the same enterprise operating system.

## 2. Design principles

NEXUS One is an enterprise ERP/MES for operational work. The design system prioritizes:

- clarity before decoration;
- workflow visibility before dashboard density;
- consistent actions before page-specific creativity;
- readable information hierarchy;
- fast keyboard/scanner-based operation;
- progressive disclosure for advanced details;
- stable layout during loading and navigation;
- meaningful semantic color rather than decorative color;
- accessibility and reduced-motion support;
- reusable primitives and long-term maintainability.

A screen should answer: **Where am I? What is happening? What can I do? What is blocked? What happens next?**

## 3. Executable theme architecture

The runtime theme is already centralized.

### Files

- `frontend/src/index.css`
- `frontend/src/context/ThemeContext.tsx`
- `frontend/src/design-system/components/shell/ThemeSelector.tsx`

### Runtime behavior

`ThemeProvider` writes the selected theme to `document.documentElement.dataset.theme`. Dark-family themes additionally toggle the `.dark` class so existing Tailwind `dark:` variants continue to work.

Theme choice is persisted through:

- `nexusone.theme`
- `nexusone.theme.mode`

The default named theme is `casterly-light`.

Do not implement another theme context or per-page theme switch.

## 4. Current named themes

The current theme registry contains nine named themes:

| Theme ID | Label | Family | Notes |
|---|---|---|---|
| `casterly-light` | Casterly Light | Light | Default theme; uses base token definitions |
| `executive-white` | Executive White | Light | Neutral monochrome enterprise palette |
| `ocean-blue` | Ocean Blue | Light | Blue/indigo with teal accent |
| `slate-professional` | Slate Professional | Light | Slate-led enterprise palette |
| `graphite-dark` | Graphite Dark | Dark | Designed dark theme; toggles `.dark` |
| `midnight-blue` | Midnight Blue | Dark | Indigo/blue dark theme; toggles `.dark` |
| `emerald` | Emerald | Light | Emerald/teal palette |
| `purple-enterprise` | Purple Enterprise | Light | Violet/indigo palette |
| `casterly-erp-green` | Casterly ERP Green | Light | Green/neutral palette; explicitly uses the light sidebar option |

Theme inventory is product behavior. Do not remove or rename a theme casually because stored user preferences depend on theme IDs.

## 5. Brand colors versus interactive theme colors

The code intentionally separates **Casterly brand identity** from **selected UI palette**.

### Casterly brand tokens

Current brand values in `index.css` include:

- Brand navy family, anchored by `brand-700: #2b2459`
- Brand violet/lavender, `brand-500: #524e9f`
- Casterly lime, `brand-lime: #c3d05b`

These are appropriate for literal Casterly/NEXUS branding surfaces and brand marks.

### Interactive theme tokens

Normal application controls should use `primary`, `secondary`, `accent`, and semantic status tokens. This lets buttons, focus rings, active navigation and component emphasis adapt when the user changes themes.

**Do not hardcode the Casterly logo navy into every primary button.**

## 6. Default Casterly Light palette

The current default interactive palette is a calm enterprise green family:

- `primary-600: #678b27`
- `secondary-100: #eef4e1`
- default theme accent: `#06b6d4`
- background: `#f9faf9`
- surface: `#ffffff`
- border: `#e2e5dc`
- text: `#1d301d`

Use the token/class names, not the literal values, in components.

## 7. Semantic color contract

Semantic meaning must remain stable even when the selected theme changes.

| Meaning | Semantic family | Typical use |
|---|---|---|
| Primary action/current selection | `primary` | Main CTA, active nav, focus, selected state |
| Secondary emphasis | `secondary` | Supporting emphasis, secondary surfaces |
| Accent/info highlight | `accent` | Small highlight, upload/secondary emphasis; avoid large fills |
| Success | Emerald / success tokens | Completed, passed, healthy, approved |
| Warning | Amber / warning tokens | Waiting, caution, conditional attention |
| Danger | Ruby/red / danger tokens | Failed, destructive, blocked-danger |
| Information | Blue / info tokens | Informational state, neutral system guidance |
| Neutral | Slate/neutral tokens | Inactive, not-applicable, secondary metadata |

Do not use color as the only state indicator. Pair it with text, icon, label, or structure.

## 8. Typography

### Primary application typeface

The global sans stack is **Poppins**, followed by reliable system fallbacks.

Use normal Tailwind font weights and the shared typography utilities rather than page-specific font-family declarations.

### Machine identifiers

NEXUS One defines a dedicated mono stack for machine identifiers:

- serial numbers;
- CLY/asset identifiers;
- certificate numbers;
- work-order numbers;
- lot/reference numbers where appropriate.

Use the existing `.text-mono-id` utility for identifiers when suitable.

### Shared type utilities

Current global utilities include:

- `.text-display`
- `.text-headline`
- `.text-title`
- `.text-eyebrow`
- `.text-numeric`
- `.text-mono-id`

Do not invent a different heading scale inside one module.

## 9. Spacing and density

The existing frontend intentionally follows Tailwind's base-4 spacing rhythm:

`4 / 8 / 16 / 24 / 32 / 40 / 48 / 64 px`

Prefer standard spacing steps such as `p-1`, `p-2`, `p-4`, `p-6`, `p-8`, etc. Avoid arbitrary values such as `p-[13px]` or `mt-[7px]` unless the layout genuinely requires a measured exception.

Operational screens should be information-dense but not cramped. Preserve scanability and touch/keyboard usability.

## 10. Radius and surfaces

Current radius tokens:

- `radius-sm: 0.375rem`
- `radius-md: 0.5rem`
- `radius-lg: 0.75rem`
- `radius-xl: 1rem`
- `radius-2xl: 1.25rem`

Use existing Card/Dialog/Table/Form primitives rather than choosing arbitrary radii per page.

The application canvas uses the shared `.app-atmosphere` treatment through `AppShell`; do not recreate background gradients on individual pages.

## 11. Elevation and shadow

Current design-system shadows include:

- `shadow-card`
- `shadow-soft`
- `shadow-soft-lg`
- `shadow-float`
- `shadow-tier-resting`
- `shadow-tier-raised`
- `shadow-tier-overlay`
- semantic glow tokens

Use stronger elevation for overlays and temporary floating surfaces, not normal content blocks.

## 12. Motion

Current global durations:

- fast: `120ms`
- base: `180ms`
- slow: `280ms`

The shared premium easing curve is `cubic-bezier(0.16, 1, 0.3, 1)`.

`AppShell` currently provides a subtle route transition and the CSS contains shared entrance, skeleton and ripple motion.

Motion must:

- communicate state or continuity;
- remain fast;
- never delay operational work;
- respect `prefers-reduced-motion`.

Do not add looping decorative animation to transactional screens.

## 13. Buttons

Use `frontend/src/design-system/components/ui/button.tsx`.

Available variants currently include:

- `default`
- `secondary`
- `outline`
- `ghost`
- `destructive`
- `link`
- `success`
- `info`
- `accent`

Typical sizing:

- default: 36px height
- small: 32px
- large: 40px
- icon: 36×36px

### Action hierarchy

A screen should normally have one visually dominant primary action. Secondary, informational, save-draft, view-history and destructive actions must not compete equally.

Use destructive styling only for genuinely destructive operations.

## 14. Badges and statuses

Use the shared `Badge` component. Current badges are fully rounded, bordered, small, uppercase/letter-spaced status indicators.

Available semantic variants include default, slate, success, warning, destructive, info and outline.

Do not make a page-specific badge system.

## 15. Forms

Prefer shared primitives under `frontend/src/design-system/components/ui/` and `smart-form/`, including:

- `form.tsx`
- `form-section.tsx`
- `form-actions.tsx`
- `labeled-field.tsx`
- `input.tsx`
- `select.tsx`
- `textarea.tsx`
- `checkbox.tsx`
- SmartForm components where they match the use case

Rules:

- group fields by business concept;
- prefill known values;
- distinguish required, conditional and optional data;
- show validation near the field;
- preserve user input on recoverable API failure;
- do not expose raw 409/422 errors as the primary UI message;
- long forms should support draft/recovery when business flow requires it.

## 16. Tables and queues

Prefer:

- `EnterpriseTable`
- `SearchFilterBar`
- `Pagination`
- `BulkActionBar`
- `RowActionButton`
- `EmptyState`

Operational queues must prioritize columns that help a user act:

**Record/Asset → Current Stage → Owner → Blocker → Age/SLA → Next Action**

Do not add dozens of low-value columns when detail can live in a drawer or Asset 360.

Server-side pagination/filtering should be used for large datasets; do not fetch thousands of rows only to filter them in the browser.

## 17. Dialogs, sheets, drawers and tabs

Use existing Radix/ShadCN-pattern primitives under `design-system/components/ui/`.

- **Dialog** — short focused confirmation/transaction.
- **Sheet/Drawer** — contextual inspection or work while retaining queue context.
- **Full page** — complex task, deep-linkable record, or broad workspace.
- **Tabs** — related views of the same object, not a substitute for navigation between business stages.

Do not create custom overlay behavior when a shared primitive already exists.

## 18. Page anatomy

Normal authenticated screens run inside `AppShell`.

Use shared page primitives and preserve this hierarchy where applicable:

1. Breadcrumb
2. Page Header / record identity
3. Primary action and status context
4. Search/filter/action bar
5. Main content/table/workbench
6. Supporting information
7. Activity/history when relevant

Do not recreate the shell, page width, or global background inside a page.

## 19. Accessibility

Required:

- visible `focus-visible` treatment;
- keyboard-accessible controls;
- accessible labels for icon-only controls;
- semantic form/table/dialog markup;
- focus restoration when overlays close;
- color-independent state meaning;
- adequate contrast in every named theme;
- reduced-motion compliance;
- responsive behavior that keeps primary actions reachable.

## 20. What must never become page-specific

Do not introduce page-local versions of:

- theme provider;
- primary palette;
- status palette;
- button system;
- badge system;
- card system;
- table shell;
- dialog/sheet behavior;
- typography scale;
- global route animation;
- dark-mode handling;
- sidebar appearance rules.

If a shared primitive genuinely cannot support a required use case, extend it carefully and preserve compatibility.
