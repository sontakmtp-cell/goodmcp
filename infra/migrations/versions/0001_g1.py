"""G1 frozen foundation, private tables with RLS and tenant composite foreign keys."""
from alembic import op
from goodmcp.schema_v1 import metadata, install_rls

revision = "0001_g1"
down_revision = None


def upgrade():
    connection = op.get_bind()
    metadata.create_all(connection)
    install_rls(connection)


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore or forward-migrate instead")
