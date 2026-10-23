"""enforce audit log immutability at db level

Revision ID: 6f52078ce90f
Revises: 107fdf906a61
Create Date: 2026-08-24 14:57:36.695798

Foundation Core Module 8 ("Audit record immutability") was previously
enforced only at the application/routing layer: no UPDATE/DELETE route or
repository function exists for audit_logs. That stops the API, but not a
raw SQL client, a future generic "bulk update" admin endpoint, or a
db.query(AuditLog).update(...) call added by mistake somewhere else in the
codebase.

This adds a real backstop: a BEFORE UPDATE OR DELETE trigger on audit_logs
that raises unconditionally, regardless of which role or code path attempts
the mutation. INSERT is untouched — audit_service.record_audit_event still
writes normally. This does not replace the application-layer guarantee
(no route to even try this exists); it closes the gap for everything that
isn't the application.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6f52078ce90f'
down_revision: Union[str, Sequence[str], None] = '107fdf906a61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs rows are immutable: % is not permitted on row id %',
                TG_OP, OLD.id;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation();")
