"""Static inventory only: never import plugin modules or deserialize pickle."""
import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def scan(root):
    packages = []
    for package in sorted(p for p in root.iterdir() if p.is_dir()):
        files, modules, refs, manifests = [], [], [], []
        for p in sorted(package.rglob("*")):
            if p.is_symlink():
                raise ValueError(f"Symlink needs review: {p}")
            if not p.is_file():
                continue
            rel = p.relative_to(package).as_posix()
            files.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha(p)})
            if p.name == "plugin.json":
                manifests.append({"path": rel, "value": json.loads(p.read_text(encoding="utf-8-sig"))})
            if p.suffix == ".py":
                tree = ast.parse(p.read_text(encoding="utf-8-sig"))
                imports = set()
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        imports.update(a.name for a in n.names)
                    elif isinstance(n, ast.ImportFrom):
                        imports.add(n.module or "")
                modules.append({"path": rel, "imports": sorted(imports),
                                "functions": [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
                                "active": "_backup_zh" not in p.parts})
            if p.suffix == ".md":
                text = p.read_text(encoding="utf-8-sig")
                for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text):
                    target = match[1].split("#")[0].strip("<>")
                    if not target or "://" in target or target.startswith(("mailto:", "#")):
                        continue
                    resolved = p.parent / target
                    refs.append({"from": rel, "target": target, "exists": resolved.exists(),
                                 "active": "_backup_zh" not in p.parts})
        roles = [f["path"] for f in files if
                 (f["path"].startswith("agents/") and f["path"].endswith(".md")) or
                 (f["path"].startswith("skills/") and f["path"].endswith("/SKILL.md"))]
        tree_hash = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        packages.append({"directory": package.name, "tree_sha256": tree_hash,
                         "file_count": len(files), "bytes": sum(f["bytes"] for f in files),
                         "extensions": dict(Counter(Path(f["path"]).suffix.lower() for f in files)),
                         "roles": roles, "manifests": manifests, "python": modules,
                         "markdown_references": refs, "files": files})
    return {"algorithm": "SHA256(canonical JSON sorted file path/bytes/sha256 list)",
            "zip_sources": "No original ZIP supplied; directory snapshots only", "packages": packages}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--compare", type=Path)
    args = ap.parse_args()
    result = scan(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.compare:
        assert result == json.loads(args.compare.read_text(encoding="utf-8")), "Plugin source changed"
    print(json.dumps([{k: v for k, v in p.items() if k in ("directory", "tree_sha256", "file_count", "bytes", "roles")} for p in result["packages"]], ensure_ascii=False))
