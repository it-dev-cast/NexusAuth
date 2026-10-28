"""PII masking for audit snapshots (Foundation Core Module 8).

Doc requirements covered here: "PII marking in audit (email, phone fields)"
and "Sensitive data masking in logs". Audit rows store a before/after
snapshot of a record — this is exactly the kind of place a raw bank account
number or password hash could leak into a table half the admin team can
query, so every snapshot passes through mask_pii() before it's serialized.
"""
import json

# Fields that get fully redacted — never even a fragment leaves the app.
_REDACT_FULLY = {
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "refresh_token",
}

# PII classification — the one list every masking rule reads from.
#   ADMIN_ONLY_PII: government ID and bank numbers. Shown in full only to
#     administrators (app/routes/employee.py), every admin read is audited.
#   PII_FIELDS: everything personal. Masked in audit snapshots and never
#     echoed back in validation errors (main.py).
ADMIN_ONLY_PII = frozenset({"pan_number", "aadhaar_number", "bank_account_number"})
PII_FIELDS = ADMIN_ONLY_PII | {
    "email",
    "contact_email",
    "attempted_email",
    "contact_phone",
    "phone_number",
    "bank_ifsc",
    "residence_proof_reference",
    "photo_reference",
}
# Never shown even partly anywhere: credentials.
SECRET_FIELDS = frozenset({"password", "password_hash", "current_password", "new_password", "refresh_token"})

# Fields that get partially masked — keep the last 4 characters so an admin
# reading the trail can still recognise "was this the same value", without
# the value itself ever being reconstructable from the audit log.
_MASK_PARTIAL = PII_FIELDS


def mask_value(value: str, keep: int = 4) -> str:
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


def mask_pii(data: dict | None) -> dict | None:
    if data is None:
        return None
    masked = {}
    for key, value in data.items():
        if value is None:
            masked[key] = None
        elif key in _REDACT_FULLY:
            masked[key] = "***REDACTED***"
        elif key in _MASK_PARTIAL and isinstance(value, str):
            masked[key] = mask_value(value)
        else:
            masked[key] = value
    return masked


def serialize_snapshot(data: dict | None) -> str | None:
    masked = mask_pii(data)
    if masked is None:
        return None
    return json.dumps(masked, default=str)
