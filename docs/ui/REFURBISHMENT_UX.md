> ⚠️ **Reference only — does not describe this repository.** This document is a snapshot from a separate, larger codebase (`NexusOne-CoreFoundation`, React + `frontend/src/...`, multi-theme design system). **nexusAuth has none of that** — its real frontend is plain HTML/CSS/JS under `frontend/` (see [CURRENT_STATE.md](CURRENT_STATE.md) for what actually exists). Kept here for reference in case nexusAuth is ever folded into that larger platform.

---

# NEXUS One Refurbishment UX Contract

## 1. Purpose

This document defines the **operator-facing UX rules** for Refurbishment. It does not redefine backend business rules. The UI must reflect the canonical workflow and help floor users act without knowing NEXUS One internals.

## 2. Non-negotiable PULSE separation

PULSE Diagnostics is an independent technical diagnostic/reference capability.

PULSE is **not** a mandatory numbered Refurbishment workflow stage.

Inside Refurbishment, PULSE may appear as:

`PULSE Diagnostic Reference — Read Only`

PULSE may inform decisions, but it must not automatically:

- create Work Orders;
- prove repair occurred;
- pass Final QC;
- assign a final grade;
- certify an asset;
- move an asset to stock;
- auto-scrap/harvest an asset.

Do not blend PULSE history into the final refurbished state. Preserve as-received diagnostic history separately.

## 3. Canonical operating journey

The physical business journey begins before Refurbishment:

`PO → GRN → Asset Registration → Engineer may run PULSE independently`

The guided Refurbishment journey then follows the canonical business/state logic currently implemented, including:

`Triage → Data Wipe according to policy → Repair/Refurbish (or Not Required) → Clean & Restore → Final QC → Grading/Certification → Packing → Stock-In`

Branches include Waiting for Parts, QC Rework, Economic Review, Harvest and Scrap according to authorized business rules.

Never reorder stages visually unless the underlying canonical workflow is deliberately changed.

## 4. Mandatory workflow header

Every asset execution screen/workbench should make these visible without requiring another tab:

- Asset identity: CLY, serial, make/model
- Current Stage
- User-friendly Status
- Current Owner/team
- Current Assignee when applicable
- Stage Age / SLA where available
- Blocker(s)
- Next Action
- Next Owner/team

Do not bury Next Action and blockers in a secondary Overview tab.

## 5. Guided stepper

Use the existing shared stepper/pipeline pattern.

States should communicate:

- Completed
- Current
- Ready
- Blocked
- Not Required

Do not show PULSE as `Step X of Y` in this stepper.

## 6. Triage

Triage is the Refurbishment team's structured initial assessment/decision stage. It must not be labeled generically as PULSE Diagnostics.

Use structured fields for business-critical observations and controlled decisions. Notes supplement structured data; they do not replace it.

Conditional requirements should be visible before submission.

Examples:

- Liquid damage → explanation/evidence required
- Scrap/Harvest → authorized reason required
- No Repair Required → should not create a meaningless Work Order

## 7. Repair decision and plan

PULSE suggestions, Triage findings, engineer findings and QC rework findings must remain visibly attributable to their source.

A human confirms/modifies the Repair Plan.

A Work Order represents actual operational repair and must not be automatically created merely because PULSE found a failure.

## 8. Technician workbench

Reuse the existing domain components such as:

- PULSE diagnostic reference
- Repair Plan Builder
- Repair Task Checklist
- Repair Parts Overview
- Repair Timer
- outcome confirmation

The technician should be able to understand the repair without opening unrelated modules.

Display:

- reported/confirmed problem;
- tasks;
- mandatory/open status;
- required/issued/installed parts;
- timer/state;
- technician findings;
- blocker;
- next action.

## 9. Waiting for Parts

A Waiting for Parts asset must clearly show:

- which mandatory part is missing;
- request/reference;
- requested/available/issued status;
- blocker age/wait duration where available;
- current owner;
- what can happen next.

Do not present `Continue Repair` as the main action when mandatory parts are unavailable.

## 10. Clean & Restore

This stage captures the **final refurbished configuration and restoration result**.

Known identity/specification data should be prefilled. Do not force retyping of CPU/RAM/storage/serial data if the system already owns a reliable value.

Use actual attachment upload controls for evidence; do not ask an operator to paste image URLs.

Preserve the distinction:

- As Received
- Final Refurbished Configuration

## 11. Final QC

Final QC independently verifies final condition. PULSE results may be displayed as read-only technical reference but cannot auto-populate a PASS decision as authoritative final QC.

QC should support:

- structured checklist categories;
- PASS / FAIL / NOT APPLICABLE where appropriate;
- model-aware applicability where available;
- inspector/timestamps;
- defects/failure reason;
- notes/evidence;
- draft save;
- attempt history.

Never overwrite earlier QC failures.

## 12. QC failure and rework

`QC FAIL → Rework Required`

The UI must route directly to the appropriate rework context/queue. Failed checks should create or support structured rework tasks using the existing repair architecture.

After rework, route to Re-QC as required.

Do not send QC-failed assets to Grading.

## 13. Grading and commercial pricing

Operational Grading and Commercial Pricing are separate responsibilities.

Grading should capture final condition/grade according to configured business policy. A grader without pricing permission must not be required to enter or see privileged commercial fields.

Do not use historical PULSE failure as proof of the final grade; final verified condition/QC owns final quality status.

## 14. Certification

Certification should reuse existing asset, final configuration, QC, grade and Data Wipe references. Do not make operators re-enter identifiers/specifications already stored in NEXUS One.

Certificate history should be traceable through Asset 360.

## 15. Packing

Packing UI should confirm the device, required accessories, labels, packaging and evidence according to the asset/policy.

Conditional requirements are essential: an accessory that does not apply must not block completion.

If a required charger is missing, show a clear packing blocker and resolution path rather than a raw validation code.

## 16. Stock-In

Stock-In should use controlled Warehouse/Zone/Rack/Bin selection from the existing location hierarchy. Do not rely on free-text location entry when master data exists.

After Stock-In, show an unambiguous terminal Refurbishment result such as `Refurbishment Complete / In Stock / Ready for Sale` according to canonical terminology.

## 17. Queues

Refurbishment operational queues should use the shared table/pagination/bulk patterns and canonical queue logic.

Priority columns:

- CLY / serial / model
- current stage/status
- owner/assignee
- blocker
- stage age/SLA
- priority
- Next Action

Command Center card counts and queue results must be generated from the same canonical criteria.

## 18. Scanner / Next Asset

Floor operations should support exact asset scan/search and production-line continuation.

A normal queue flow should support:

`Open/Scan → Act → Complete/Handoff → Next Asset`

without requiring the operator to close several screens and search again.

## 19. Bulk assignment

Bulk assignment/reassignment/handover is a supervisor operation. It must:

- use role-valid assignees;
- preserve assignment history;
- report partial failures clearly;
- refresh the queue without a full browser reload;
- respect backend RBAC.

Bulk speed must never replace individual validation for Triage, repair completion, QC, grading, packing, Stock-In or destructive decisions.

## 20. Economic review / destructive branches

Economic Review, Harvest and Scrap are explicit human/authorized decisions.

Do not visually imply an automatic destructive outcome from AI/PULSE/economic indicators.

High-impact actions must be separated from normal primary actions, require proper permission, and retain reason/audit evidence.

## 21. Asset 360

Asset 360 is the lifecycle/history/reference view. It should answer, from real records:

- source PO/GRN;
- registration/identity;
- PULSE history;
- Triage;
- repair plan/work order/tasks;
- parts used/component removals;
- labour/time/cost where permitted;
- final configuration;
- every QC attempt;
- grade/certificate;
- packing;
- current stock location.

Do not display `Not recorded` when the data already exists elsewhere in the application.

## 22. User-facing language

Use business terms:

- `Ready for Final QC`, not `qc_pending`
- `QC Failed — Rework Required`, not `qc_failed`
- `Waiting for Parts`, not internal enum text
- `Cannot complete repair because 1 mandatory task remains open`, not `409 Conflict`

Technical codes belong in logs/support details, not as the primary operator message.

## 23. Refurbishment visual consistency checklist

Before completing a Refurbishment UI task, verify:

- global theme inherited correctly;
- no page-specific theme colors introduced;
- workflow header visible;
- stepper uses canonical order;
- PULSE shown separately/read-only;
- Next Action visible;
- Blocker visible;
- Next Owner/handoff clear;
- one primary action;
- dangerous actions separated;
- queue context preserved;
- empty/loading/error states designed;
- keyboard/scanner workflow remains practical;
- TypeScript, ESLint and build clean.
