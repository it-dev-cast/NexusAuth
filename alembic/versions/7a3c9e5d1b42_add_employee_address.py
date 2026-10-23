"""add employee address

Revision ID: 7a3c9e5d1b42
Revises: 2b6f8e1a4c73
Create Date: 2026-09-30 00:00:00.000000

Employee page field: address. Stored through EncryptedString like
phone_number (same class of contact PII), so the column is Text: a Fernet
token is longer than the address it wraps. Nullable, no backfill.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a3c9e5d1b42"
down_revision: Union[str, Sequence[str], None] = "2b6f8e1a4c73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "address")
