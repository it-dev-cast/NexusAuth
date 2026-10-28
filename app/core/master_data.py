"""Registry of the masters shown on the Master Management page.

Two kinds:

* LIST masters (MASTER_TYPES) — plain value lists an admin can add to, rename,
  describe and deactivate. They live in one table, `master_items`
  (app/models/master_item.py), and fill dropdowns that used to be hardcoded in
  the page: Supplier Category and Payment Terms (Supplier form) and
  Application Category (Application form).

* LINKED masters (LINKED_MASTERS) — Departments, Job Roles, Applications,
  Manufacturers and Models. These already have their own tables, APIs and
  screens, so they are reused as they are (not copied into master_items);
  the Master Management page simply shows them next to the list masters.

Like every other master here, a record stores the chosen value's *name* as
text, so renaming or deactivating a value never rewrites history — which is
also why a list value's name can't be changed once something uses it.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MasterType:
    key: str  # stored in master_items.master_type; the API accepts "-" for "_"
    label: str  # singular, for headings and messages
    plural: str
    description: str
    group: str
    used_by: str  # where its values appear — shown on the page, kept honest
    parent_type: str | None = None
    parent_required: bool = False
    has_code: bool = False
    code_label: str = "Code"


MASTER_TYPES: dict[str, MasterType] = {
    t.key: t
    for t in (
        MasterType(
            key="application_category",
            label="Application Category",
            plural="Application Categories",
            description="Groups applications — for example Core, People or Operations.",
            group="People",
            used_by="Application form → Category",
        ),
        MasterType(
            key="supplier_category",
            label="Supplier Category",
            plural="Supplier Categories",
            description="What a supplier provides — for example Hardware, Software or Logistics.",
            group="Suppliers",
            used_by="Supplier form → Category",
        ),
        MasterType(
            key="payment_terms",
            label="Payment Terms",
            plural="Payment Terms",
            description="Standard payment terms offered by suppliers — for example Net 30 or Due on Receipt.",
            group="Suppliers",
            used_by="Supplier form → Terms",
        ),
    )
}

GROUP_ORDER = ("People", "Assets", "Suppliers")


def normalize_key(raw: str) -> str:
    return (raw or "").strip().lower().replace("-", "_")


def get_master_type(raw: str) -> MasterType | None:
    return MASTER_TYPES.get(normalize_key(raw))


@dataclass(frozen=True)
class LinkedMaster:
    """A master that already has its own table, API and screen."""

    key: str
    label: str
    plural: str
    description: str
    group: str
    used_by: str


LINKED_MASTERS: dict[str, LinkedMaster] = {
    m.key: m
    for m in (
        LinkedMaster(
            key="department",
            label="Department",
            plural="Departments",
            description="Departments, with an optional parent department and manager.",
            group="People",
            used_by="Employee form → Department",
        ),
        LinkedMaster(
            key="job_role",
            label="Job Role",
            plural="Job Roles",
            description="Job titles offered in the Employee form's Job role dropdown.",
            group="People",
            used_by="Employee form → Job role",
        ),
        LinkedMaster(
            key="application",
            label="Application",
            plural="Applications",
            description="Applications an employee can be given access to.",
            group="People",
            used_by="Employee form → Application access",
        ),
        LinkedMaster(
            key="manufacturer",
            label="Manufacturer",
            plural="Manufacturers",
            description="Asset manufacturers, for example Dell or HP.",
            group="Assets",
            used_by="Asset form → Manufacturer",
        ),
        LinkedMaster(
            key="asset_model",
            label="Model",
            plural="Models",
            description="Asset models, for example Latitude 5420.",
            group="Assets",
            used_by="Asset form → Model",
        ),
    )
}
