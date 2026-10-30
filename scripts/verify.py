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

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "Docs/reports/evidence/G1"


def json_tail(value):
    for line in reversed(value.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError("Expected JSON output missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["G1"], required=True)
    parser.add_argument("--working-tree", action="store_true", help="Development only; does not satisfy clean-checkout acceptance")
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    project = "goodmcp-g1-verify-" + stamp.lower()
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
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "HUB_SECRETS_DIR": str(secret_dir), "HUB_PORT": str(port), "HUB_ALLOW_TEST_FIXTURES": "1",
           "HUB_OWNER_EMAIL": "owner@local.invalid"}
    base = ["docker", "compose", "-p", project, "-f", str(source / "infra/compose.yml")]
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    commands = []
    log = []
    evidence = {"stage": "G1", "status": "in_progress", "source_commit": commit,
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
                    assert response.status == 200 and payload["data"]["stage"] == "G1"
                    return payload
            except Exception:
                if attempt == 49: raise
                time.sleep(0.2)

    try:
        run("compose-config", "config", "--quiet")
        run("build-clean-source", "build", "api", "caddy")
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
        run("start-local-stack", "up", "-d", "--wait", "api", "worker", "caddy")
        health()
        output = run("postgres-and-filesystem-tests", "run", "--rm", "--no-deps", "tests")
        match = re.search(r"(\d+) passed", output)
        assert match, "No successful pytest summary"
        evidence["checks"]["pytest_passed"] = int(match.group(1))
        before = json_tail(run("seed-persistence", "run", "--rm", "--no-deps", "tests", "python", "tests/persistence.py", "seed"))
        # Stronger than process restart: recreate every service, retaining volumes.
        run("recreate-stack-down-keep-volumes", "down")
        run("recreate-stack-up", "up", "-d", "--wait", "postgres", "api", "worker", "caddy")
        after = json_tail(run("verify-persistence", "run", "--rm", "--no-deps", "tests", "python", "tests/persistence.py", "check"))
        assert before["artifact_id"] == after["artifact_id"] and after["persisted_after_recreate"]
        evidence["checks"]["db_and_blob_persist_after_recreate"] = True
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
            ports = container["HostConfig"]["PortBindings"] or {}
            if service == "caddy":
                assert ports and all(v[0]["HostIp"] == "127.0.0.1" for v in ports.values())
            else: assert not ports, "Only Caddy may publish ports"
            mounts = container["Mounts"]
            assert all(m["Destination"] != "/var/run/docker.sock" for m in mounts)
            if service in ("api", "worker"):
                assert container["Config"]["User"] == "10001:10001" and container["HostConfig"]["ReadonlyRootfs"]
                assert all(m["Destination"].split("/")[-1] not in ("admin_password", "migrator_password", "owner_password") for m in mounts)
            services.append({"service": service, "image_id": container["Image"], "user": container["Config"]["User"],
                "ports": ports, "readonly_rootfs": container["HostConfig"]["ReadonlyRootfs"],
                "secret_names": [m["Destination"].split("/")[-1] for m in mounts if m["Destination"].startswith("/run/secrets/")]})
        evidence["services"] = services
        evidence["checks"]["only_loopback_caddy_no_admin_secrets_in_runtime"] = True
        run("cleanup-own-test-project", "down", "--volumes", "--remove-orphans")
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
    print("G1 passed: " + evidence["source_mode"] + ", " + str(evidence["checks"]["pytest_passed"]) + " PostgreSQL/filesystem tests", flush=True)


if __name__ == "__main__": main()
