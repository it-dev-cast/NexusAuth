> ⚠️ **Reference only — does not describe this repository.** This document is a snapshot from a separate, larger codebase (`NexusOne-CoreFoundation`, React + `frontend/src/...`, multi-theme design system). **nexusAuth has none of that** — its real frontend is plain HTML/CSS/JS under `frontend/` (see [CURRENT_STATE.md](CURRENT_STATE.md) for what actually exists). Kept here for reference in case nexusAuth is ever folded into that larger platform.

---

# NEXUS One Shared Component Guidelines

## 1. Principle

The NEXUS One design system already contains a substantial reusable component library. New screens must **compose existing primitives first**. Creating a visually similar but separate implementation is considered design drift.

Before creating a component, search:

`frontend/src/design-system/components/`

## 2. Component layers

Use this mental model:

### Layer A — UI primitives

Path: `frontend/src/design-system/components/ui/`

Current primitives include Button, Badge, Card, Input, Select, Textarea, Checkbox, Label, Dialog, Sheet, Tabs, Dropdown Menu, Popover, Tooltip, Skeleton, Alert, Avatar, Form, FormSection, FormActions, InspectorPanel and related helpers.

Use these for low-level consistent visual behavior.

### Layer B — shell/navigation

Path: `frontend/src/design-system/components/shell/`

Important components include:

- `AppShell`
- `AppSidebar`
- `Topbar`
- `PageContainer`
- `PageHeader`
- `Breadcrumb`
- `GlobalSearch`
- `NotificationsMenu`
- `ProfileMenu`
- `ThemeSelector`
- `ContextualHelpDrawer`
- `BrandHeader` / `BrandMark`

A page must not create a second application shell.

### Layer C — data and CRUD

Paths:

- `design-system/components/data/`
- `design-system/components/crud/`

Important patterns include:

- `EnterpriseTable`
- `Pagination`
- `SearchFilterBar`
- `BulkActionBar`
- `EmptyState`
- `SavedFilters`
- `KanbanBoard`
- `CrudListPage`
- `CrudForm`
- `ViewDetailsPage`
- `SearchToolbar`
- `FilterPanel`
- `StandardActionButtons`

Use these before building a bespoke list/search/pagination toolbar.

### Layer D — operational/dashboard components

Path: `design-system/components/dashboard/`

Important shared components include StatCard, KpiSection, WorkflowPipeline, MyTasksPanel, SlaMonitoring, Timeline, TechnicianWorkload, ActivityFeed and chart/card primitives.

Use these for operational summaries, not decorative dashboards.

### Layer E — domain components

Examples:

- `design-system/components/refurbishment/`
- `design-system/components/warranty/`
- `design-system/components/sales/`
- `design-system/components/reporting/`

Domain components may encode presentation patterns specific to that business area while still consuming the global primitives.

## 3. Component selection decision tree

Before writing JSX for a new screen:

1. **Is this application shell/navigation?** Use shell components.
2. **Is this a list/queue?** Use EnterpriseTable + shared search/pagination/bulk primitives.
3. **Is this a standard CRUD form?** Check CRUD and SmartForm components.
4. **Is this a short focused action?** Use Dialog.
5. **Is this contextual record work/details?** Prefer Sheet/Drawer if retaining queue context matters.
6. **Is this a complex, shareable/deep-linkable workbench?** Use a full page.
7. **Is the pattern already implemented in the same domain?** Extend/reuse it rather than clone it.

## 4. Reuse before wrapper creation

Do not create wrappers such as `MyGreenButton`, `CustomCard`, `NewStatusBadge` merely to apply a page-specific class set.

A wrapper is justified when it adds a stable domain concept or behavior, not just different spacing/color.

Examples of valid domain components:

- `PulseDiagnosticReference`
- `RepairPlanBuilder`
- `RepairTaskChecklist`
- `RepairPartsOverviewTable`
- `RepairTimerCard`

These represent real operational concepts, not alternative base controls.

## 5. Page header

Use `PageHeader` for normal page title/description/action hierarchy. Do not repeat a large custom title block above it.

For record/workflow pages, pair it with business status/identity context rather than replacing it with a giant decorative hero.

## 6. Table rules

For new operational tables:

- use server-side pagination for large datasets;
- keep selection state explicit;
- preserve filters/page/sort when opening and returning from a record where practical;
- use `BulkActionBar` for multi-select actions;
- use `EmptyState` rather than blank grids;
- use row actions consistently;
- do not hide critical actionability behind horizontal scrolling if a compact column can represent it.

## 7. Button rules

Use shared Button variants according to intent.

- Primary business completion/continue → `default` (or `success` when the semantic meaning is specifically approval/completion and the existing pattern uses it)
- Secondary action → `secondary` / `outline`
- Tertiary/local action → `ghost`
- Destructive → `destructive`
- Informational → `info`
- Accent/supporting emphasis → `accent`

Do not choose color based on personal preference.

## 8. Status rules

Use one semantic label and one semantic tone for the same business state throughout the application.

Avoid exposing raw values such as `qc_failed` or `awaiting_parts` when the UI can show `QC Failed — Rework Required` or `Waiting for Parts`.

## 9. Error/loading/empty patterns

Every component that performs asynchronous work must define:

- initial loading;
- local action loading;
- empty result;
- recoverable error;
- permission denial;
- successful completion.

Prefer Skeleton for content loading and Button `isLoading` for action loading.

Errors must preserve entered data where possible.

## 10. Component extension policy

When a shared component is close but insufficient:

1. inspect all current call sites;
2. add a backward-compatible prop or variant;
3. keep the default behavior unchanged;
4. add tests when behavior is non-trivial;
5. update this documentation if the extension changes the component contract.

Do not perform a global redesign as a side effect of one screen request.

## 11. Styling policy

Preferred order:

1. existing component variant/prop;
2. semantic Tailwind token class;
3. existing shared CSS utility;
4. small local layout class adjustment;
5. only then consider a new token or shared primitive.

Avoid hardcoded hex, one-off gradients, custom shadows, arbitrary pixel spacing, and component-local dark theme logic.

## 12. Testing shared UI work

At minimum validate:

- TypeScript;
- ESLint;
- production build;
- relevant component/route tests;
- keyboard focus;
- default light theme;
- Graphite Dark or Midnight Blue;
- one alternate light palette if the component uses primary/secondary/accent heavily;
- responsive layout at common laptop/tablet widths.
