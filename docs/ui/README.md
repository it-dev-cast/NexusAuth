> ⚠️ **Reference only — does not describe this repository.** This document is a snapshot from a separate, larger codebase (`NexusOne-CoreFoundation`, React + `frontend/src/...`, multi-theme design system). **nexusAuth has none of that** — its real frontend is plain HTML/CSS/JS under `frontend/` (see [CURRENT_STATE.md](CURRENT_STATE.md) for what actually exists). Kept here for reference in case nexusAuth is ever folded into that larger platform.

---

# NEXUS One UI / Theme System — Developer Entry Point

> Source snapshot: `NexusOne-CoreFoundation(20260817-074826).zip` (17 Aug 2026)

This folder is the **developer-facing UI contract** for NEXUS One. It does not replace the executable theme in code. It explains how developers and AI coding agents must use the theme that already exists in the application.

## 1. Source-of-truth hierarchy

Use this order when there is any ambiguity:

1. **Business/workflow behavior** — backend rules and canonical workflow engines.
2. **Executable UI/theme implementation** — `frontend/src/index.css`, `frontend/src/context/ThemeContext.tsx`, and shared components under `frontend/src/design-system/components/`.
3. **This documentation** — rules for using and extending the executable implementation consistently.
4. Existing broad references — `docs/UI_UX_MASTER_GUIDE.md` and `docs/UI_UX_GUIDELINES.md`.

If documentation and the current executable design system disagree, do not silently invent a third behavior. Verify the current code and update the documentation or implementation deliberately.

## 2. Developers should NOT manually "apply a theme" to every screen

NEXUS One already applies themes globally through CSS variables and shared components. A page should normally inherit the selected theme automatically.

**Correct model:**

`ThemeContext` → `data-theme` + `.dark` → CSS tokens in `index.css` → shared design-system components → pages

Developers should build screens from shared primitives and semantic Tailwind classes. They should not copy color values from this Markdown into individual pages.

## 3. What to read for each type of task

| Task | Required reading |
|---|---|
| Backend-only work | No UI/theme document required |
| Small existing-screen UI change | `DESIGN_SYSTEM.md` + relevant component source |
| New screen or major layout | `DESIGN_SYSTEM.md` + `COMPONENT_GUIDELINES.md` |
| Sidebar, shell, menus, breadcrumbs, routing UX | `DESIGN_SYSTEM.md` + `NAVIGATION_UX.md` |
| Refurbishment UI | `DESIGN_SYSTEM.md` + `REFURBISHMENT_UX.md` |
| New theme / palette / dark-mode change | `DESIGN_SYSTEM.md` + `THEME_IMPLEMENTATION_GUIDE.md` |
| New reusable component | `COMPONENT_GUIDELINES.md` + nearest existing shared component |

Do **not** load every UI Markdown file for every coding task. Read only the relevant contract.

## 4. Mandatory rules for all frontend work

1. Reuse `frontend/src/design-system/components/` before creating a page-local component.
2. Use theme/semantic classes and CSS tokens; do not introduce page-specific hex colors for normal UI.
3. Never create a second theme provider, second token system, or page-level dark-mode system.
4. Preserve all named themes unless a change explicitly targets theme inventory.
5. Use `PageHeader`, `Breadcrumb`, `PageContainer`, shared table/form/dialog primitives, and shared workflow components where applicable.
6. One screen must not visually redefine buttons, badges, cards, tables, spacing, typography, or status semantics.
7. Use business language, not raw backend status codes.
8. Loading, empty, error, permission, disabled, and responsive states are part of the screen definition.
9. Theme changes must work in both light and dark families and respect reduced-motion preferences.
10. Refurbishment screens must follow the guided workflow contract in `REFURBISHMENT_UX.md`.
11. Navigation/menu work must follow `NAVIGATION_UX.md` and RBAC; hiding a menu is never a substitute for backend authorization.
12. Do not copy a reference product literally. Adapt patterns to the NEXUS One/Casterly design language.

## 5. Current implementation anchors

- Global CSS/theme tokens: `frontend/src/index.css`
- Theme registry/persistence: `frontend/src/context/ThemeContext.tsx`
- Theme picker: `frontend/src/design-system/components/shell/ThemeSelector.tsx`
- Authenticated shell: `frontend/src/design-system/components/shell/AppShell.tsx`
- Sidebar/navigation data: `frontend/src/design-system/components/shell/AppSidebar.tsx`, `nav-items.ts`
- Page primitives: `PageHeader.tsx`, `PageContainer.tsx`, `Breadcrumb.tsx`
- Table primitives: `EnterpriseTable.tsx`, `Pagination.tsx`, `SearchFilterBar.tsx`, `BulkActionBar.tsx`, `EmptyState.tsx`
- Form/UI primitives: `frontend/src/design-system/components/ui/`
- Refurbishment shared components: `frontend/src/design-system/components/refurbishment/`

## 6. Definition of done for UI changes

A frontend task is not complete until:

- it inherits all supported themes without page-specific repair work;
- it uses existing shared components where suitable;
- light/dark contrast is readable;
- loading/empty/error/permission states are handled;
- keyboard focus is visible;
- reduced motion is respected;
- no raw status/error codes are exposed as the primary user message;
- TypeScript, ESLint and production build remain clean;
- the relevant business workflow is not changed merely for visual convenience.
