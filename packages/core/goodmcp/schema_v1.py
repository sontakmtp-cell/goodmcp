"""Frozen G1 schema for Alembic revision 0001_g1. Append migrations, do not edit after release."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = sa.MetaData()


def ident():
    return sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def created():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def payload(name="metadata", default="{}"):
    return sa.Column(name, JSONB, nullable=False, server_default=sa.text(f"'{default}'::jsonb"))


def ref(column, parent, *, nullable=False):
    return (sa.Column(column, UUID(as_uuid=True), nullable=nullable),
            sa.ForeignKeyConstraint(["workspace_id", column], [f"{parent}.workspace_id", f"{parent}.id"]))


def actor(column="user_id"):
    return (sa.Column(column, UUID(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id", column], ["memberships.workspace_id", "memberships.user_id"]))


users = sa.Table("users", metadata, ident(),
    sa.Column("email", sa.Text, nullable=False, unique=True),
    sa.Column("password_hash", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()), created())
workspaces = sa.Table("workspaces", metadata, ident(), sa.Column("name", sa.Text, nullable=False), created())
memberships = sa.Table("memberships", metadata, ident(),
    sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.CheckConstraint("role IN ('owner','admin','member','viewer')"),
    sa.UniqueConstraint("workspace_id", "id"), sa.UniqueConstraint("workspace_id", "user_id"), created())

private_tables = []


def private(name, *columns):
    table = sa.Table(name, metadata, ident(),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        *columns, sa.UniqueConstraint("workspace_id", "id"), created())
    private_tables.append(name)
    return table


private("plugin_packages", sa.Column("name", sa.Text, nullable=False), sa.Column("license", sa.Text),
        sa.UniqueConstraint("workspace_id", "name"), payload())
private("plugin_versions", *ref("package_id", "plugin_packages"),
        sa.Column("manifest_version", sa.Text, nullable=False), sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_artifact_id", UUID(as_uuid=True)), payload(),
        sa.UniqueConstraint("workspace_id", "package_id", "manifest_version", "source_sha256"))
private("installations", *ref("plugin_version_id", "plugin_versions"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()), payload())
for name in ("skills", "agents"):
    private(name, *ref("plugin_version_id", "plugin_versions"), sa.Column("name", sa.Text, nullable=False),
            sa.Column("body", sa.Text, nullable=False), sa.UniqueConstraint("workspace_id", "plugin_version_id", "name"))
private("projects", *ref("plugin_version_id", "plugin_versions", nullable=True),
        sa.Column("name", sa.Text, nullable=False), sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
        payload("state"), sa.CheckConstraint("revision >= 0"))
private("artifacts", *ref("project_id", "projects", nullable=True), *actor("created_by_user_id"),
        sa.Column("sha256", sa.String(64), nullable=False), sa.Column("bytes", sa.BigInteger, nullable=False),
        sa.Column("media_type", sa.Text, nullable=False), sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pin_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("bytes >= 0 AND revision > 0 AND pin_count >= 0"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'"))
# Source package blob pointer is nullable until G3 importer publishes the source artifact.
metadata.tables["plugin_versions"].append_constraint(sa.ForeignKeyConstraint(
    ["workspace_id", "source_artifact_id"], ["artifacts.workspace_id", "artifacts.id"],
    name="fk_source_artifact", use_alter=True))
private("resources", *ref("plugin_version_id", "plugin_versions"), *ref("artifact_id", "artifacts", nullable=True),
        sa.Column("logical_path", sa.Text, nullable=False), payload(),
        sa.UniqueConstraint("workspace_id", "plugin_version_id", "logical_path"))
private("tool_bindings", *ref("plugin_version_id", "plugin_versions"),
        sa.Column("mcp_name", sa.Text, nullable=False), sa.Column("adapter_id", sa.Text, nullable=False),
        sa.Column("image_digest", sa.Text, nullable=False), payload("input_schema"), payload("output_schema"),
        payload("limits"), sa.Column("network_policy", sa.Text, nullable=False, server_default="none"),
        sa.Column("file_policy", sa.Text, nullable=False, server_default="plugin-ro_index-ro_job-rw"),
        sa.CheckConstraint("image_digest ~ '^sha256:[0-9a-f]{64}$'"),
        sa.UniqueConstraint("workspace_id", "plugin_version_id", "mcp_name"))
private("stage_commits", *ref("project_id", "projects"), *actor(),
        sa.Column("revision", sa.Integer, nullable=False), sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("decision", sa.Text, nullable=False), payload("assumptions", default="[]"),
        sa.CheckConstraint("revision > 0"),
        sa.UniqueConstraint("workspace_id", "project_id", "revision"),
        sa.UniqueConstraint("workspace_id", "project_id", "idempotency_key"))
private("jobs", *actor(), *ref("project_id", "projects", nullable=True),
        *ref("plugin_version_id", "plugin_versions", nullable=True), *ref("binding_id", "tool_bindings", nullable=True),
        sa.Column("type", sa.Text, nullable=False), sa.Column("operation", sa.Text, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.Text, nullable=False),
        payload("input"), sa.Column("state", sa.Text, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.Text), sa.Column("lease_token", UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)), sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        *ref("result_artifact_id", "artifacts", nullable=True), sa.Column("error_code", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('queued','running','succeeded','failed','cancelled')"),
        sa.CheckConstraint("attempts >= 0 AND max_attempts BETWEEN 1 AND 3 AND attempts <= max_attempts"),
        sa.CheckConstraint("state != 'succeeded' OR (result_artifact_id IS NOT NULL AND finished_at IS NOT NULL AND error_code IS NULL)"),
        sa.CheckConstraint("state != 'failed' OR (error_code IS NOT NULL AND finished_at IS NOT NULL)"),
        sa.CheckConstraint("state != 'cancelled' OR finished_at IS NOT NULL"),
        sa.CheckConstraint("state NOT IN ('queued','running') OR (result_artifact_id IS NULL AND finished_at IS NULL AND error_code IS NULL)"),
        sa.CheckConstraint("state != 'running' OR (started_at IS NOT NULL AND attempts > 0)"),
        sa.UniqueConstraint("workspace_id", "operation", "idempotency_key"))
private("job_attempts", *ref("job_id", "jobs"), sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("lease_token", UUID(as_uuid=True), nullable=False), payload("result"),
        sa.UniqueConstraint("workspace_id", "job_id", "attempt"))
private("audit_events", *actor(), sa.Column("action", sa.Text, nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False), payload("details"))
private("connections", *actor(), sa.Column("name", sa.Text, nullable=False), payload())
private("oauth_grants", *actor(), *ref("connection_id", "connections", nullable=True),
        sa.Column("client_id", sa.Text, nullable=False), payload("scopes", default="[]"),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
private("tokens", *ref("grant_id", "oauth_grants"),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
private("host_profiles", *ref("connection_id", "connections"), payload("capabilities"),
        sa.Column("requested_model", sa.Text), sa.Column("reported_model", sa.Text),
        sa.Column("evidence_at", sa.DateTime(timezone=True)))


def install_rls(connection):
    execute = lambda query: connection.execute(sa.text(query))
    uid = "NULLIF(current_setting('app.user_id', true), '')::uuid"
    wid = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
    execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    execute("GRANT USAGE ON SCHEMA public TO hub_runtime")
    for name in ("users", "workspaces", "memberships", *private_tables):
        execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
    execute(f"CREATE POLICY self_user ON users FOR SELECT TO hub_runtime USING (id={uid} AND active)")
    execute(f"CREATE POLICY self_membership ON memberships FOR SELECT TO hub_runtime USING (user_id={uid} AND active AND EXISTS (SELECT 1 FROM users u WHERE u.id=memberships.user_id AND u.active))")
    execute(f"CREATE POLICY own_workspace ON workspaces FOR SELECT TO hub_runtime USING (EXISTS (SELECT 1 FROM memberships m WHERE m.workspace_id=workspaces.id AND m.user_id={uid} AND m.active))")
    execute("GRANT SELECT(id,email,active,created_at) ON users TO hub_runtime")
    execute("GRANT SELECT ON workspaces,memberships,alembic_version TO hub_runtime")
    admin_tables = {"plugin_packages", "plugin_versions", "installations", "skills", "agents", "resources", "tool_bindings"}
    for name in private_tables:
        readable = f"workspace_id={wid} AND EXISTS (SELECT 1 FROM memberships m WHERE m.workspace_id={name}.workspace_id AND m.user_id={uid} AND m.active)"
        roles = "'owner','admin'" if name in admin_tables else "'owner','admin','member'"
        writable = f"({readable}) AND EXISTS (SELECT 1 FROM memberships m WHERE m.workspace_id={name}.workspace_id AND m.user_id={uid} AND m.active AND m.role IN ({roles}))"
        execute(f'CREATE POLICY tenant_read ON "{name}" FOR SELECT TO hub_runtime USING ({readable})')
        execute(f'CREATE POLICY tenant_insert ON "{name}" FOR INSERT TO hub_runtime WITH CHECK ({writable})')
        if name != "audit_events":
            execute(f'CREATE POLICY tenant_update ON "{name}" FOR UPDATE TO hub_runtime USING ({writable}) WITH CHECK ({writable})')
            execute(f'CREATE POLICY tenant_delete ON "{name}" FOR DELETE TO hub_runtime USING ({writable})')
            execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON "{name}" TO hub_runtime')
        else:
            execute('GRANT SELECT,INSERT ON audit_events TO hub_runtime')
        execute(f'CREATE INDEX "ix_{name}_workspace" ON "{name}"(workspace_id)')
