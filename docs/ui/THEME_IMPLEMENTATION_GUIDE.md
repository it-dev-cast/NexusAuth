> ⚠️ **Reference only — does not describe this repository.** This document is a snapshot from a separate, larger codebase (`NexusOne-CoreFoundation`, React + `frontend/src/...`, multi-theme design system). **nexusAuth has none of that** — its real frontend is plain HTML/CSS/JS under `frontend/` (see [CURRENT_STATE.md](CURRENT_STATE.md) for what actually exists). Kept here for reference in case nexusAuth is ever folded into that larger platform.

---

# NEXUS One Theme Implementation Guide

## 1. Purpose

This is the implementation guide for extending or maintaining the **existing NEXUS One named-theme system**. It is not a proposal for a new theming library.

## 2. Current architecture

### Registry and persistence

`frontend/src/context/ThemeContext.tsx`

Responsibilities:

- defines the `THEMES` registry;
- stores selected theme ID;
- stores Light/Dark/System mode;
- applies `data-theme` to `<html>`;
- toggles `.dark` for dark-family themes;
- follows OS preference in System mode.

### Tokens

`frontend/src/index.css`

Tailwind v4 is configured CSS-first with `@theme`. The file contains:

- typography stacks;
- Casterly brand palette;
- primary/secondary/accent scales;
- semantic colors;
- radius/duration/shadow/tracking tokens;
- default theme semantic surface values;
- named `:root[data-theme="..."]` override blocks;
- dark theme blocks;
- global atmosphere/motion/accessibility utilities.

### Theme selection UI

`frontend/src/design-system/components/shell/ThemeSelector.tsx`

The picker reads from the same `THEMES` array, preventing a separate hardcoded theme list.

## 3. Adding a new named theme

Do this only for a product-approved theme.

### Step 1 — add registry entry

Add one `ThemeDefinition` in `ThemeContext.tsx`:

```ts
{ id: "new-theme", label: "New Theme", emoji: "…", dark: false }
```

For a theme that intentionally requires the light sidebar behavior currently supported by the shell, use the existing optional `sidebarStyle` property rather than custom sidebar CSS in pages.

Theme IDs are persisted in localStorage. Treat IDs as stable public product identifiers.

### Step 2 — add CSS variable override block

In `index.css`, add:

```css
:root[data-theme="new-theme"] {
  --color-primary-50: ...;
  /* full primary scale */

  --color-secondary-50: ...;
  /* full secondary scale */

  --color-accent-50: ...;
  /* full accent scale */

  --color-theme-primary: ...;
  --color-theme-secondary: ...;
  --color-theme-accent: ...;
  --color-theme-background: ...;
  --color-theme-surface: ...;
  --color-theme-border: ...;
  --color-theme-text: ...;

  --color-atmosphere-base: ...;
  --color-atmosphere-glow-a: ...;
  --color-atmosphere-glow-b: ...;
  --color-atmosphere-glow-c: ...;
}
```

A dark theme should follow the existing `:root[data-theme="..."].dark` pattern and explicitly define readable dark semantic surface/input/muted values where required.

### Step 3 — do not modify normal components

A correctly implemented theme should apply because components already consume token classes such as `primary-*`, `secondary-*`, `accent-*`, semantic state colors and dark variants.

If adding a theme requires editing dozens of screens, the implementation is probably bypassing the token architecture.

## 4. What a theme may change

A named theme may change:

- primary palette;
- secondary palette;
- accent palette;
- background/surface/border/text;
- subtle application atmosphere;
- approved sidebar style option;
- dark-family behavior.

A named theme should **not** change:

- workflow order;
- component geometry arbitrarily;
- table behavior;
- page layout;
- RBAC/navigation structure;
- button meanings;
- success/warning/danger business semantics;
- PULSE/Refurbishment architecture.

Theme is visual language, not business logic.

## 5. Semantic tokens versus literal values

Pages should prefer token classes:

```tsx
className="bg-primary-600 text-white hover:bg-primary-700"
```

not:

```tsx
style={{ background: "#678b27" }}
```

Brand mark surfaces may intentionally use `brand-*` tokens.

Status meaning should use success/warning/danger/info patterns, not whatever the selected theme's primary color happens to be.

## 6. Dark themes

Current dark-family themes are `graphite-dark` and `midnight-blue`.

`ThemeContext` toggles `.dark` for these themes. Existing `dark:` Tailwind variants are therefore part of the current architecture.

Do not add a second dark-mode attribute or a page-level `isDark` state.

When changing shared components, verify both dark themes because their palettes/surfaces differ.

## 7. System mode

System mode currently follows `prefers-color-scheme` and resolves to:

- `casterly-light` for light OS preference;
- `graphite-dark` for dark OS preference.

Do not make System mode randomly select another palette.

## 8. Sidebar behavior

The sidebar historically has its own structural styling. The theme model includes an optional `sidebarStyle: "dark" | "light"` extension point, and `casterly-erp-green` currently opts into the light style.

Do not create page-level sidebar overrides.

## 9. Theme-safe component checklist

A shared component is theme-safe when:

- primary emphasis uses theme tokens;
- surface/text/border have readable light and dark behavior;
- semantic states use semantic colors;
- focus rings remain visible;
- hover/selected/disabled states remain distinguishable;
- no literal white/black assumption breaks another theme unless the surface is intentionally fixed;
- charts/visualizations remain legible if they consume theme colors;
- reduced-motion remains respected.

## 10. Theme QA matrix

For any change to shared styles/components, validate at least:

1. Casterly Light — default production baseline
2. Casterly ERP Green — alternate green/light-sidebar behavior
3. Graphite Dark — primary dark baseline
4. Midnight Blue — second dark palette
5. One non-green light palette such as Ocean Blue or Purple Enterprise when the change affects primary/secondary/accent usage

Check:

- text/background contrast;
- cards/surfaces/borders;
- buttons and focus rings;
- badges/statuses;
- inputs/selects/dropdowns;
- dialogs/sheets;
- tables/selected rows;
- sidebar/topbar;
- empty/loading/error states;
- disabled state;
- print/export preview only if affected.

## 11. Theme change regression

Run:

- TypeScript
- ESLint
- production frontend build
- relevant frontend/component tests

For CSS/token changes, perform live browser spot checks in the QA matrix above.

Do not treat a successful build as proof of visual contrast/readability.

## 12. Hardcoded-color policy

The current codebase contains historical hardcoded colors in some specialized components/visualizations. Do not expand that pattern in normal product UI.

When touching an existing hardcoded value:

- if it is normal product chrome/control styling, migrate to an appropriate token where safe;
- if it is a deliberate data-series/illustration/brand asset color, document the reason and keep it localized;
- do not launch an unrelated global color refactor from a small feature task.

## 13. Theme documentation maintenance

When the theme inventory or core token architecture changes, update:

- `ThemeContext.tsx`
- `index.css`
- this guide
- `DESIGN_SYSTEM.md` theme table

Do not let documentation become a second stale theme registry.
