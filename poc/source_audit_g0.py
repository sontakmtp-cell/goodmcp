"""Static supplied-index/corpus audit: stdlib only, never unpickle or import plugin."""
import ast
import collections
import json
import zipfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
root = repo / "plugin_example/vietnam-finance-tax-expert/references/corpus/vietnam-finance-tax-corpus"
metadata = json.loads((root / "chunks_metadata.json").read_text(encoding="utf-8"))
manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
arrays = []
with zipfile.ZipFile(root / "tfidf_matrix.npz") as z:
    for name in z.namelist():
        with z.open(name) as f:
            assert f.read(6) == b"\x93NUMPY"
            version = f.read(2)
            width = 2 if version[0] == 1 else 4
            size = int.from_bytes(f.read(width), "little")
            assert 0 < size < 65536
            header = ast.literal_eval(f.read(size).decode("latin1"))
            arrays.append({"name": name, "header": header, "uncompressed_bytes": z.getinfo(name).file_size})
files = manifest["files"]
result = {"scope": "Static JSON/ZIP/NPY header parsing only; no pickle deserialization",
          "original_metadata_rows": len(metadata), "original_metadata_fields": list(metadata[0]),
          "original_matrix_arrays": arrays, "manifest_entries": len(files),
          "manifest_missing": [x["filename"] for x in files if not (root / x["filename"]).is_file()],
          "manifest_size_mismatches": [x["filename"] for x in files if (root / x["filename"]).is_file()
                                       and (root / x["filename"]).stat().st_size != x["size_bytes"]],
          "txt": len(list(root.glob("*.txt"))), "html": len(list(root.glob("*.html"))),
          "pdf": len(list(root.glob("*.pdf"))), "short_txt_skipped": [p.name for p in root.glob("*_short.txt")]}
output = repo / "Docs/reports/evidence/G0/source-audit.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"original_rows": len(metadata), "manifest_missing": len(result["manifest_missing"]),
                  "manifest_size_mismatches": len(result["manifest_size_mismatches"]), "output": str(output)}))

run_file = repo / "Docs/reports/evidence/G0/run.json"
if run_file.exists():
    run_id = json.loads(run_file.read_text(encoding="utf-8"))["run_id"]
    work = repo / ".g0-local" / run_id
    if (work / "chunks_metadata.json").is_file():
        rebuilt = json.loads((work / "chunks_metadata.json").read_text(encoding="utf-8"))
        ids = collections.Counter(x["id"] for x in rebuilt)
        composite = collections.Counter((x["source_file"], x["id"]) for x in rebuilt)
        full_rows = 0
        with (work / "chunks_full.jsonl").open(encoding="utf-8") as stream:
            for row, line in zip(rebuilt, stream, strict=True):
                full = json.loads(line)
                assert all(full[k] == v for k, v in row.items())
                assert full["text"][:200] == row["preview"] and len(full["text"]) == row["char_count"]
                full_rows += 1
        identity = {"run_id": run_id, "rebuilt_rows": len(rebuilt), "unique_legacy_ids": len(ids),
                    "duplicate_legacy_id_groups": sum(v > 1 for v in ids.values()),
                    "duplicate_legacy_id_extra_rows": len(rebuilt) - len(ids),
                    "unique_composite_source_file_id": len(composite),
                    "composite_collisions": sum(v > 1 for v in composite.values()),
                    "full_text_rows_rechecked": full_rows}
        (output.parent / "chunk-identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(identity))
