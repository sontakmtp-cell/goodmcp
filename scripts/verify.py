"""G1 acceptance on a fresh git-archive source, isolated Compose project and volumes.

Never touches existing app data or plugin_example. Only deletes containers/volumes
belonging to the randomly named verification project, after saving safe evidence.
Failure retains this test project's state for diagnosis; all secrets stay ignored.
"""
import argparse
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.request
import uuid
import zipfile
import sys

if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]


def json_tail(value):
    for line in reversed(value.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError("Expected JSON output missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["G1", "G2", "G3"], required=True)
    parser.add_argument("--working-tree", action="store_true", help="Development only; does not satisfy clean-checkout acceptance")
    args = parser.parse_args()
    EVIDENCE = ROOT / "Docs/reports/evidence" / args.stage
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    project = "goodmcp-" + args.stage.lower() + "-verify-" + stamp.lower()
    scratch = ROOT / ".local/verify" / stamp
    source = scratch / "source"
    scratch.mkdir(parents=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if args.working_tree:
        source = ROOT
    else:
        archive = subprocess.check_output(["git", "archive", "--format=zip", "HEAD"], cwd=ROOT)
        source.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            for name in zipped.namelist():
                resolved = (source / name).resolve()
                if not resolved.is_relative_to(source.resolve()): raise RuntimeError("Unsafe archive path")
            zipped.extractall(source)
        if not (source / "infra/compose.yml").is_file():
            raise RuntimeError("Commit G1 source first; clean checkout does not contain G1 yet")
    setup_spec = importlib.util.spec_from_file_location("setup_local", ROOT / "scripts/setup-local.py")
    setup_module = importlib.util.module_from_spec(setup_spec)
    setup_spec.loader.exec_module(setup_module)
    secret_dir = setup_module.setup(scratch / "secrets")
    sample_dir = scratch / "samples"
    sample_dir.mkdir()
    if args.stage == "G3":
        spec = importlib.util.spec_from_file_location("pack_g3", source / "scripts/pack-g3-samples.py")
        pack_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(pack_module)
        # Input fixtures live outside git; verified archived code still builds cleanly.
        pack_module.ROOT = ROOT
        pack_module.pack(sample_dir)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "HUB_SECRETS_DIR": str(secret_dir), "HUB_PORT": str(port), "HUB_ALLOW_TEST_FIXTURES": "1", "HUB_G3_SAMPLES_DIR": str(sample_dir),
           "HUB_IMAGE": project + "-hub:verified", "HUB_CADDY_IMAGE": project + "-caddy:verified",
           "HUB_OWNER_EMAIL": "owner@local.invalid", "HUB_PUBLIC_BASE_URL": "http://localhost:8080"}
    base = ["docker", "compose", "-p", project, "-f", str(source / "infra/compose.yml")]
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    commands = []
    log = []
    evidence = {"stage": args.stage, "status": "in_progress", "source_commit": commit,
                "source_mode": "working_tree_dev" if args.working_tree else "clean_git_archive",
                "run_id": stamp, "project": project, "checks": {}, "commands": commands}

    def run(label, *command):
        print(label, flush=True)
        start = time.monotonic()
        completed = subprocess.run(base + list(command), cwd=source, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        commands.append({"label": label, "argv": list(command), "exit_code": completed.returncode,
                         "elapsed_s": round(time.monotonic() - start, 3)})
        log.append("\n[" + label + "]\n" + completed.stdout + completed.stderr)
        if completed.returncode:
            print((completed.stdout + completed.stderr)[-10000:])
            raise RuntimeError(label + " failed")
        return completed.stdout

    def admin(operation):
        return json_tail(run("admin-" + operation, "run", "--rm", "--no-deps", "admin", "python", "-m", "goodmcp.admin", operation))

    def health():
        for attempt in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=3) as response:
                    payload = json.load(response)
                    assert response.status == 200 and payload["data"]["stage"] in ("G1", "G2", "G3")
                    return payload
            except Exception:
                if attempt == 49: raise
                time.sleep(0.2)

    try:
        run("compose-config", "config", "--quiet")
        run("build-clean-source", "build", "api", "caddy")
        built_images = {key: subprocess.check_output(["docker", "image", "inspect", env[key], "--format", "{{.Id}}"], text=True).strip()
                        for key in ("HUB_IMAGE", "HUB_CADDY_IMAGE")}
        evidence["built_images"] = built_images
        run("start-empty-postgres", "up", "-d", "--wait", "postgres")
        admin("roles")
        run("api-before-migration", "up", "-d", "--no-deps", "api")
        run("readiness-denies-missing-migration", "run", "--rm", "--no-deps", "tests", "python", "tests/readiness.py", "503")
        run("migration-up", "run", "--rm", "--no-deps", "migrate")
        run("migration-idempotent", "run", "--rm", "--no-deps", "migrate")
        first, second = admin("owner"), admin("owner")
        assert first["created"] and not second["created"] and first["workspace_id"] == second["workspace_id"]
        initial = admin("inspect")
        assert initial["users"] == initial["workspaces"] == 1
        evidence["checks"]["single_owner_bootstrap_idempotent"] = True
        admin("fixtures")
        if args.stage in ("G2", "G3"):
            run("auth-workspace-fixture", "run", "--rm", "--no-deps", "auth_probe")
        run("start-local-stack", "up", "-d", "--wait", "api", "auth", "worker", "caddy")
        health()
        output = run("postgres-and-filesystem-tests", "run", "--rm", "--no-deps", "tests")
        match = re.search(r"(\d+) passed", output)
        assert match, "No successful pytest summary"
        evidence["checks"]["pytest_passed"] = int(match.group(1))
        if args.stage == "G3":
            result = json_tail(run("plugin-import-and-catalog-wire", "run", "--rm", "--no-deps", "wire", "python", "tests/wire_g3.py", "full"))
            assert result["passed"]
            evidence["g3_wire"] = result
            evidence["g3_memory"] = {}
            for service in ("api", "worker"):
                observation = json_tail(run("import-memory-" + service, "exec", "-T", service, "python", "-c",
                    "import json; from pathlib import Path; p=Path('/sys/fs/cgroup'); print(json.dumps({'peak_bytes':int((p/'memory.peak').read_text()),'events':(p/'memory.events').read_text()}))"))
                assert "oom_kill 0" in observation["events"]
                evidence["g3_memory"][service] = observation
        if args.stage in ("G2", "G3"):
            result = json_tail(run("oauth-mcp-wire-full", "run", "--rm", "--no-deps", "wire"))
            assert result["passed"]
            evidence["wire_full"] = result
            run("oauth-negative-fixtures", "run", "--rm", "--no-deps", "auth_probe", "python", "-m", "goodmcp.auth_admin", "negatives")
            result = json_tail(run("oauth-wire-negative-tokens", "run", "--rm", "--no-deps", "wire", "python", "tests/wire_g2.py", "negatives"))
            assert result["passed"]
            evidence["wire_negatives"] = result
        before = json_tail(run("seed-persistence", "run", "--rm", "--no-deps", "tests", "python", "tests/persistence.py", "seed"))
        # Stronger than process restart: recreate every service, retaining volumes.
        run("recreate-stack-down-keep-volumes", "down")
        run("recreate-stack-up", "up", "-d", "--wait", "postgres", "api", "auth", "worker", "caddy")
        after = json_tail(run("verify-persistence", "run", "--rm", "--no-deps", "tests", "python", "tests/persistence.py", "check"))
        assert before["artifact_id"] == after["artifact_id"] and after["persisted_after_recreate"]
        evidence["checks"]["db_and_blob_persist_after_recreate"] = True
        if args.stage in ("G2", "G3"):
            result = json_tail(run("oauth-survives-recreate", "run", "--rm", "--no-deps", "wire", "python", "tests/wire_g2.py", "resume"))
            assert result["passed"]
            evidence["wire_resume"] = result
            evidence["credential_storage"] = json_tail(run("inspect-credential-storage", "run", "--rm", "--no-deps", "auth_probe", "python", "-m", "goodmcp.auth_admin", "inspect"))
        if args.stage == "G3":
            result = json_tail(run("plugin-versions-survive-recreate", "run", "--rm", "--no-deps", "wire", "python", "tests/wire_g3.py", "resume"))
            assert result["passed"]
            evidence["g3_resume"] = result
        health()
        run("stop-db-for-negative-health", "stop", "postgres")
        run("readiness-denies-db-outage", "run", "--rm", "--no-deps", "tests", "python", "tests/readiness.py", "503")
        run("recover-db", "up", "-d", "--wait", "postgres")
        for _ in range(50):
            try:
                health()
                break
            except Exception: time.sleep(0.1)
        else: raise RuntimeError("Readiness did not recover")
        evidence["checks"]["health_missing_migration_db_outage_recovery"] = True
        evidence["database"] = admin("inspect")
        ids = run("container-ids", "ps", "-q").splitlines()
        inspected = json.loads(subprocess.check_output(["docker", "inspect", *ids], cwd=source))
        services = []
        for container in inspected:
            service = container["Config"]["Labels"]["com.docker.compose.service"]
            if service in ("api", "auth", "worker", "caddy"):
                assert container["Image"] == built_images["HUB_CADDY_IMAGE" if service == "caddy" else "HUB_IMAGE"]
            ports = container["HostConfig"]["PortBindings"] or {}
            if service == "caddy":
                assert ports and all(v[0]["HostIp"] == "127.0.0.1" for v in ports.values())
            else: assert not ports, "Only Caddy may publish ports"
            mounts = container["Mounts"]
            assert all(m["Destination"] != "/var/run/docker.sock" for m in mounts)
            if service in ("api", "worker"):
                assert container["Config"]["User"] == "10001:10001" and container["HostConfig"]["ReadonlyRootfs"]
                assert all(m["Destination"].split("/")[-1] not in ("admin_password", "migrator_password", "owner_password") for m in mounts)
            if service == "auth":
                assert [m["Destination"] for m in mounts if m["Destination"].startswith("/run/secrets/")] == ["/run/secrets/auth_password"]
            services.append({"service": service, "image_id": container["Image"], "user": container["Config"]["User"],
                "ports": ports, "readonly_rootfs": container["HostConfig"]["ReadonlyRootfs"],
                "secret_names": [m["Destination"].split("/")[-1] for m in mounts if m["Destination"].startswith("/run/secrets/")]})
        evidence["services"] = services
        evidence["checks"]["only_loopback_caddy_no_admin_secrets_in_runtime"] = True
        # Activate the test profile for down as well: otherwise Compose can retain
        # the profile-only wire_state volume containing temporary test credentials.
        run("cleanup-own-test-project", "--profile", "test", "--profile", "ops", "down", "--volumes", "--remove-orphans")
        leftovers = subprocess.check_output(["docker", "volume", "ls", "--filter", "label=com.docker.compose.project=" + project, "--format", "{{.Name}}"], text=True).strip()
        assert not leftovers, "Verification project volumes were not fully removed"
        evidence["checks"]["all_test_volumes_removed"] = True
        evidence["status"] = "passed"
    except Exception:
        evidence["status"] = "failed"
        raise
    finally:
        encoded = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        console = "".join(log)
        for path in secret_dir.iterdir():
            value = path.read_text(encoding="utf-8").strip()
            if value in encoded or value in console:
                raise RuntimeError("Secret found in evidence; refusing to publish")
        (EVIDENCE / "verify.json").write_text(encoded, encoding="utf-8")
        (EVIDENCE / "verify-console.txt").write_text(console, encoding="utf-8")
    print(args.stage + " passed: " + evidence["source_mode"] + ", " + str(evidence["checks"]["pytest_passed"]) + " PostgreSQL/filesystem tests", flush=True)


if __name__ == "__main__": main()
