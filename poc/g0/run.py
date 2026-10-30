"""Reproduce G0 only. Host needs Python 3.12+ (stdlib only) and Docker Linux.

Build may download locked libraries. Executed plugins have no network. Each run
gets a new scratch directory, never reusing supplied or previously built pickle.
"""
import datetime
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from inventory import scan

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "Docs/reports/evidence/G0"


def call(args, **kwargs):
    print("+ " + " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, cwd=ROOT, **kwargs)


def write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    work = ROOT / ".g0-local" / run_id
    work.mkdir(parents=True)
    # Linux host bind mount must permit the fixed non-root UID. Contains no secrets.
    work.chmod(0o777)
    before = scan(ROOT / "plugin_example")
    write("inventory-before.json", before)
    call(["docker", "build", "-t", "goodmcp-g0:local", "poc/g0"])
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", "goodmcp-g0:local"], cwd=ROOT))[0]
    docker_info = json.loads(subprocess.check_output(["docker", "info", "--format", "{{json .}}"], cwd=ROOT))
    base = ["docker", "run", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "128", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,source={ROOT / 'plugin_example'},target=/plugins,readonly",
            "--mount", f"type=bind,source={ROOT / 'Docs/contracts'},target=/contracts,readonly",
            "--mount", f"type=bind,source={work},target=/work"]
    states = []
    try:
        for mode, limits, command in (
            ("bench", ["--cpus", "4", "--memory", "5g", "--memory-swap", "5g"], ["python", "benchmark.py"]),
            ("auth", ["--cpus", "1", "--memory", "512m", "--memory-swap", "512m"], ["python", "wire_smoke.py"]),
            ("contract", ["--cpus", "1", "--memory", "256m", "--memory-swap", "256m"],
             ["python", "check_contract.py", "--schema", "/contracts/g0.schema.json", "--output", "/work/contract-check.json"]),
            ("cap-search", ["--cpus", "2", "--memory", "3g", "--memory-swap", "3g"], ["python", "benchmark.py", "search"]),
            ("cap-light", ["--cpus", "1", "--memory", "256m", "--memory-swap", "256m"], ["python", "benchmark.py", "calculators"]),
        ):
            name = f"goodmcp-g0-{mode}-{run_id.lower()}"
            try:
                with (EVIDENCE / f"{mode}-console.txt").open("w", encoding="utf-8") as log:
                    call(base + ["--name", name] + limits + [image["Id"]] + command, stdout=log, stderr=subprocess.STDOUT)
                if mode.startswith("cap-"):
                    shutil.copyfile(work / ("search.json" if mode == "cap-search" else "calculators.json"), work / f"{mode}.json")
            finally:
                raw = subprocess.check_output(["docker", "inspect", name], cwd=ROOT)
                item = json.loads(raw)[0]
                states.append({"name": mode, "image_id": item["Image"], "state": item["State"],
                    "limits": {k: item["HostConfig"][k] for k in ("Memory", "MemorySwap", "NanoCpus", "PidsLimit", "NetworkMode", "ReadonlyRootfs", "CapDrop", "SecurityOpt")},
                    "mounts": [{"destination": m["Destination"], "rw": m["RW"]} for m in item["Mounts"]]})
                call(["docker", "rm", name])  # Only this run's exited containers, retain scratch artifacts.
    finally:
        after = scan(ROOT / "plugin_example")
        write("inventory-after.json", after)
        write("run.json", {"run_id": run_id, "image_id": image["Id"], "image_size_bytes": image["Size"],
            "docker": {k: docker_info[k] for k in ("ServerVersion", "OperatingSystem", "KernelVersion", "Architecture", "NCPU", "MemTotal")},
            "source_unchanged": before == after, "containers": states})
        for pattern in ("benchmark.json", "wire-auth*.json", "contract-check.json", "cap-*.json", "calculators.json", "refs.json", "smoke_more.json", "build.json", "search.json", "trusted-index.json", "[0-9]-*.txt"):
            for p in work.glob(pattern): shutil.copyfile(p, EVIDENCE / p.name)
        assert before == after, "plugin_example changed"
    summary = json.loads((work / "benchmark.json").read_text(encoding="utf-8"))
    wire = json.loads((work / "wire-auth.json").read_text(encoding="utf-8"))
    assert summary["passed"] and wire["passed"]
    print(f"G0 local passed; evidence: {EVIDENCE}; rebuildable index: {work}")


if __name__ == "__main__": main()
