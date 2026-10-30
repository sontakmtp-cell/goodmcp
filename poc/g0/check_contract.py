"""Check normative JSON schema and boundary examples, not future DB/runtime."""
import argparse
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

parser = argparse.ArgumentParser()
parser.add_argument("--schema", type=Path, default=Path("Docs/contracts/g0.schema.json"))
parser.add_argument("--output", type=Path, default=Path("Docs/reports/evidence/G0/contract-check.json"))
args = parser.parse_args()
schema = json.loads(args.schema.read_text(encoding="utf-8"))
Draft202012Validator.check_schema(schema)
uid = "00000000-0000-4000-8000-000000000001"
validators = {name: Draft202012Validator({**schema, "$ref": f"#/$defs/{name}"}, format_checker=FormatChecker())
              for name in schema["$defs"]}
request = {"binding_id": uid, "arguments": {"revenue": 100, "cost": 40}, "idempotency_key": "fixture-0001"}
validators["InvocationRequest"].validate(request)
checks = ["schema-valid", "invocation-valid"]
for field, value in (("workspace_id", uid), ("command", "echo x"), ("image", "arbitrary:latest"), ("mount", "/")):
    assert not validators["InvocationRequest"].is_valid({**request, field: value}), field
    checks.append("reject-invocation-" + field)
job = {"id": uid, "state": "queued", "attempts": 0,
       "created_at": "2026-10-30T00:00:00Z", "deadline_at": "2026-10-30T00:01:00Z"}
validators["PublicJob"].validate(job)
for state in ("succeeded", "failed", "cancelled", "running"):
    assert not validators["PublicJob"].is_valid({**job, "state": state}), state
    checks.append("reject-incomplete-job-" + state)
validators["PublicJob"].validate({**job, "state": "succeeded", "attempts": 1,
    "result_artifact_id": uid, "finished_at": "2026-10-30T00:00:30Z"})
assert not validators["PublicJob"].is_valid({**job, "result_artifact_id": uid})
assert not validators["PublicJob"].is_valid({**job, "lease_owner": "secret-internal-worker"})
artifact = {"id": uid, "sha256": "a" * 64, "bytes": 1, "media_type": "text/plain", "revision": 1,
            "created_at": "2026-10-30T00:00:00Z"}
validators["ArtifactDescriptor"].validate(artifact)
assert not validators["ArtifactDescriptor"].is_valid({**artifact, "storage_key": "../../tenant-b"})
assert not validators["InvocationRequest"].is_valid({**request, "binding_id": "not-a-uuid"})
checks += ["success-needs-artifact", "queued-no-output", "no-lease-leak", "artifact-valid", "no-storage-key-leak", "uuid-format"]
result = {"passed": True, "checks": checks, "scope": "schema and examples only; not DB isolation or executable sandbox tests"}
args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
