"""Create deterministic local ZIP snapshots without changing supplied plugin folders."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/core"))
from goodmcp.plugin_scan import tree_hash, safe_path


def pack(destination):
    destination = Path(destination).resolve(); destination.mkdir(parents=True, exist_ok=True)
    packages = []
    baseline_path = ROOT / "Docs/reports/evidence/G0/inventory-before.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    for folder in sorted((ROOT / "plugin_example").iterdir(), key=lambda p: p.name):
        if not folder.is_dir(): continue
        files = {}
        paths = sorted(folder.rglob("*"), key=lambda p: p.relative_to(folder).as_posix().encode("utf-8"))
        for p in paths:
            if p.is_symlink(): raise RuntimeError("Symlink in source")
            if not p.is_file(): continue
            path = safe_path(p.relative_to(folder).as_posix())
            h = hashlib.sha256()
            with p.open("rb") as f:
                while b := f.read(1024*1024): h.update(b)
            files[path] = {"bytes": p.stat().st_size, "sha256": h.hexdigest()}
        if baseline:
            old = next(x for x in baseline["packages"] if x["directory"] == folder.name)
            assert {x["path"]: {k: x[k] for k in ("bytes", "sha256")} for x in old["files"]} == files
        target = destination / (folder.name + ".zip")
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for p in paths:
                if not p.is_file(): continue
                rel = p.relative_to(folder).as_posix()
                entry = zipfile.ZipInfo(rel, date_time=(1980,1,1,0,0,0)); entry.create_system=3
                entry.external_attr = (stat.S_IFREG | 0o444) << 16
                with p.open("rb") as source, z.open(entry, "w", force_zip64=True) as out:
                    while b := source.read(1024*1024): out.write(b)
        h = hashlib.sha256()
        with target.open("rb") as f:
            while b := f.read(1024*1024): h.update(b)
        packages.append({"directory": folder.name, "zip": target.name, "zip_sha256": h.hexdigest(),
                         "zip_bytes": target.stat().st_size, "tree_sha256": tree_hash(files), "files": files})
    report = {"source": "local_folder_snapshot_not_original_vendor_zip", "g0_files_rechecked": baseline is not None,
              "tree_hash_format": "goodmcp-tree-v1", "packages": packages}
    (destination / "samples.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=ROOT / ".local/g3-samples")
    result=pack(parser.parse_args().output)
    print(json.dumps({"packages":len(result["packages"]), "files":sum(len(p["files"]) for p in result["packages"]), "g0_rechecked":result["g0_files_rechecked"]}))
