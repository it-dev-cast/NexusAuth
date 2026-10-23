> ⚠️ **Reference only — does not describe this repository.** This document is a snapshot from a separate, larger codebase (`NexusOne-CoreFoundation`, React + `frontend/src/...`, multi-theme design system). **nexusAuth has none of that** — its real frontend is plain HTML/CSS/JS under `frontend/` (see [CURRENT_STATE.md](CURRENT_STATE.md) for what actually exists). Kept here for reference in case nexusAuth is ever folded into that larger platform.

---

# NEXUS One Navigation & Screen-Flow UX

## 1. Goal

NEXUS One should behave like **one guided enterprise operating system**, not a collection of disconnected modules.

A normal user should not need to memorize which sidebar screen comes after another screen.

Every important operational screen should make these answers clear:

1. Where am I?
2. Why am I here?
3. What is the current state?
4. What do I need to do now?
5. What is blocking progress?
6. What happens next?
7. Who owns the next action?

## 2. Current navigation foundations

Use the existing implementation:

- `AppShell.tsx`
- `AppSidebar.tsx`
- `nav-items.ts`
- `Breadcrumb.tsx`
- `PageHeader.tsx`
- `GlobalSearch.tsx`
- application route guards

Do not build a second navigation tree inside a domain.

## 3. Sidebar

The sidebar is a discovery and switching tool, not the primary execution engine for every transaction.

Rules:

- group screens by real business domain;
- show role-relevant items only according to the implemented RBAC model;
- do not expose internal technical names as menu labels;
- do not add a menu entry for every modal/action;
- menu badges must be backed by the same canonical logic as the destination queue;
- an undefined/missing permission rule must never become an accidental reason to expose sensitive modules;
- hiding a menu is UX only — backend authorization remains mandatory.

## 4. Breadcrumbs

Use the shared `Breadcrumb` component. Do not hand-code a different breadcrumb per page unless the route structure genuinely cannot express the business hierarchy.

Breadcrumbs provide **location**, not workflow status.

Example:

`Refurbishment > Final QC > CLY-00125`

Do not put the entire workflow into the breadcrumb.

## 5. Page headers

Normal screen headers should provide:

- title;
- concise purpose/description;
- relevant metadata;
- primary action(s) with a clear hierarchy.

Record/workflow screens should additionally surface identity and status context nearby.

## 6. Current Stage / Next Action / Blocker / Next Owner

For workflow-driven records, reuse the canonical backend/frontend workflow resolver rather than hardcoding navigation in each page.

The UI should conceptually receive one consistent contract:

- Current Stage
- User-Friendly Status
- Next Action
- Primary Route/action
- Blockers
- Next Owner/team
- Whether current user is allowed to act

Do not duplicate this logic in twenty pages.

## 7. Continue-to-next-step behavior

After a successful action, tell the user what changed and what comes next.

Examples:

- `Repair Completed → Next: Clean & Restore`
- `QC Passed → Next: Grading`
- `Packing Complete → Next: Stock-In`

If the same user has permission to continue, show a clear `Continue` action.

If another role owns the next action, show a handoff state instead:

- Next Stage
- Next Team/Owner
- Waiting status
- Return to My Tasks / View Asset 360

Do not show an unusable Continue button.

## 8. My Tasks and role queues

For daily operational users, `My Tasks` / role-specific queues should be the primary entry point.

A user should be able to:

`Login → My Tasks/Queue → Open record → Complete action → Continue or hand off → Next record`

without browsing the full sidebar between every stage.

## 9. Queue-to-record context

When an operator opens a record from a filtered queue and returns, preserve where practical:

- queue;
- page;
- search;
- filter;
- sort.

Do not dump the user onto an unrelated dashboard after completing or viewing an action.

## 10. Scanner-first behavior

For asset-centric floor flows, exact CLY/serial scanning/search should open the intended record/action quickly and should not search only the currently loaded page.

After completing a production-line stage, support `Next Asset` where the existing queue workflow provides it.

## 11. One primary action

Each screen should have one dominant action for the normal current state.

Secondary actions such as Save Draft, View History, View PULSE, Download, or Help should be visually subordinate.

Dangerous actions such as Scrap, Harvest, Reject, Cancel, Override and Delete must be separated and permission-controlled.

## 12. Blocker resolution

A blocker should not only describe a problem. If the current user can resolve it, provide the contextual resolution action.

Examples:

- `Repair Plan not confirmed` → `Confirm Repair Plan`
- `Parts request requires approval` → `Review Parts Request`
- `QC Failed` → `Open Rework`

If the user cannot resolve it, show the responsible team/owner.

## 13. Empty states

Never show an unexplained empty table.

Examples:

- `No repair tasks are currently assigned to you.`
- `No assets are ready for Final QC.`
- `No urgent operational exceptions.`

Offer the most useful permitted action, not a generic decorative illustration.

## 14. Access denied

An unauthorized route should show a clear business-friendly Access Denied state and a safe route back to My Tasks or Dashboard.

Do not expose raw JSON errors or permission internals.

## 15. Browser Back / route behavior

Back navigation must not:

- resubmit forms;
- reopen completed transactions incorrectly;
- lose saved draft data;
- unexpectedly remove queue context;
- navigate to dead grouping routes.

## 16. Screen ownership

Every major page must have one primary purpose.

Examples:

- Queue page → select/action work
- Asset Workflow → guided execution
- Work Orders → repair work management
- Asset 360 → lifecycle/history/reference
- Command Center → supervisor operational overview
- Reports → analysis/export, not transaction execution

If two pages appear to perform the same primary job, resolve the overlap rather than teaching users both.

## 17. Navigation definition of done

A workflow change is not complete if a normal user must know an undocumented route/menu sequence to continue.

Every active state must have either:

- one understandable primary next action; or
- a clear waiting/blocker/handoff/terminal state.
