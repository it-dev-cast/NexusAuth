"""widen employee PII columns for encryption at rest

Revision ID: c50668c12e48
Revises: 7e5c1f9a2d64
Create Date: 2026-08-24 00:00:00.000000

Foundation Core PII protection (SECURITY_CHECKLIST.md's flagged risk):
bank_account_number/bank_ifsc/pan_number/aadhaar_number/
residence_proof_reference/photo_reference now go through app.core.pii_crypto
(Fernet) at the ORM boundary when PII_ENCRYPTION_KEY is configured. A
Fernet token is meaningfully longer than the plain value it wraps (roughly
plaintext length + ~100 bytes of overhead, base64-encoded), so the original
bounded VARCHAR sizes (20/50/500) are too small for ciphertext. This widens
those six columns to TEXT.

This is purely a column-type widening — additive, non-destructive, and it
does not touch existing row data. It does NOT retroactively encrypt
already-stored plaintext values; those are re-encrypted the next time each
row is written (see app/core/pii_crypto.py's docstring). No backfill/data
migration is performed here, deliberately: rewriting every existing PII
value in a single migration is exactly the kind of automatic, hard-to-audit
data change the architecture asks us not to do without an explicit,
reviewed step.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c50668c12e48"
down_revision: Union[str, Sequence[str], None] = "7e5c1f9a2d64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "bank_account_number",
    "bank_ifsc",
    "pan_number",
    "aadhaar_number",
    "residence_proof_reference",
    "photo_reference",
)

_ORIGINAL_LENGTHS = {
    "bank_account_number": 50,
    "bank_ifsc": 20,
    "pan_number": 20,
    "aadhaar_number": 20,
    "residence_proof_reference": 500,
    "photo_reference": 500,
}


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "employees",
            column,
            existing_type=sa.String(length=_ORIGINAL_LENGTHS[column]),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Lossy if any stored value (ciphertext or otherwise) is currently
    # longer than the original bound — Postgres will reject the narrowing
    # ALTER in that case rather than silently truncate. That is the correct,
    # safe failure mode for a downgrade here: fix/re-encrypt-shorter or
    # accept data loss explicitly, don't let a migration decide for you.
    for column in _COLUMNS:
        op.alter_column(
            "employees",
            column,
            existing_type=sa.Text(),
            type_=sa.String(length=_ORIGINAL_LENGTHS[column]),
            existing_nullable=True,
        )
