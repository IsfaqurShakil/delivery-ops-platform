"""audit log append only

Revision ID: append_only_audit
Revises: 18fb59ca1f8c
"""
from alembic import op

revision = "append_only_audit"
down_revision = "18fb59ca1f8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) A function that always stops the change with an error.
    op.execute(
        """
        CREATE FUNCTION audit_log_block_changes() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: update, delete and truncate are not allowed';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    # 2) Run that function before any UPDATE or DELETE of a row.
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_changes()
        """
    )
    # 3) Run it before TRUNCATE (wipe the whole table) too.
    op.execute(
        """
        CREATE TRIGGER audit_log_no_truncate
        BEFORE TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block_changes()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER audit_log_no_update_delete ON audit_log")
    op.execute("DROP FUNCTION audit_log_block_changes()")
