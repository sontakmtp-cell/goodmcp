"""Linux-only local measurements of original reviewed Python code.

Cold means a fresh Python process (OS page cache is NOT flushed). Warm search
reuses one matrix. ru_maxrss is kernel process high-water RSS, not container RAM.
"""
import contextlib
import importlib.metadata
import io
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

from runtime import CORPUS, WORK, INDEX_FILES, digest, load, verified_search

QUERY = "thuế thu nhập doanh nghiệp"


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build():
    builder = load("build_index")
    builder.VECTORIZER_PATH = WORK / "tfidf_vectorizer.pkl"
    builder.MATRIX_PATH = WORK / "tfidf_matrix.npz"
    builder.META_PATH = WORK / "chunks_metadata.json"
    # Capture exact chunks produced by original function, without changing TF-IDF.
    original_chunk = builder.chunk_text
    captured = []

    def capture(text, *args, **kwargs):
        chunks = original_chunk(text, *args, **kwargs)
        captured.extend(chunks)
        return chunks

    builder.chunk_text = capture
    sys.argv = ["build_index.py", "--force"]
    builder.main()
    metadata = json.loads(builder.META_PATH.read_text())
    assert len(metadata) == len(captured)
    with (WORK / "chunks_full.jsonl").open("w", encoding="utf-8") as f:
        for row, text in zip(metadata, captured, strict=True):
            assert row["char_count"] == len(text) and row["preview"] == text[:200]
            f.write(json.dumps({**row, "text": text}, ensure_ascii=False) + "\n")
    manifest = {"builder_sha256": digest(CORPUS / "build_index.py"),
                "created_by": "reviewed builder in G0 offline container, NOT imported pickle",
                "sha256": {n: digest(WORK / n) for n in INDEX_FILES}}
    write(WORK / "trusted-index.json", manifest)
    return {"chunks": len(metadata), "source_files": len({r["source_file"] for r in metadata}),
            "full_text_rows_verified": len(captured), "manifest": manifest}


def calculators():
    c = load("calculators")
    args = {"revenue": 50_000_000_000, "cost": 38_000_000_000, "rate": 10,
            "free_years": 4, "half_years": 9, "year": 6}
    result = c.cit_estimate(**args)
    assert result["cit_with_incentive_VND"] == 600_000_000
    warm = []
    for _ in range(100):
        t = time.perf_counter()
        assert c.cit_estimate(**args) == result
        warm.append(time.perf_counter() - t)
    # Direct function baseline, not legal correctness validation.
    return {"function": "calculators.cit_estimate", "input": args, "output": result,
            "warm_calls": len(warm), "warm_median_s": statistics.median(warm), "warm_max_s": max(warm)}


def refs():
    r = load("refs")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r.show_calendar()
        r.show_odi()
    text = buf.getvalue()
    assert "LỊCH KHAI BÁO" in text and "TRÌNH TỰ ODI" in text
    warm = []
    for _ in range(5):
        t = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()) as again:
            r.show_calendar()
            r.show_odi()
        assert again.getvalue() == text
        warm.append(time.perf_counter() - t)
    return {"functions": ["refs.show_calendar", "refs.show_odi"], "chars": len(text), "output": text,
            "warm_calls": len(warm), "warm_median_s": statistics.median(warm), "warm_max_s": max(warm)}


def search():
    t = time.perf_counter()
    s = verified_search()
    idx = s.load_index()
    load_s = time.perf_counter() - t
    durations, results = [], []
    for _ in range(6):
        t = time.perf_counter()
        results = s.search(QUERY, *idx, top_k=5)
        durations.append(time.perf_counter() - t)
    assert results and all(r["score"] > 0 for r in results)
    meta = idx[2]
    known = {m["id"]: m for m in meta}
    assert all(r["chunk_id"] in known and (CORPUS / r["source_file"]).is_file() for r in results)
    return {"query": QUERY, "chunks": len(meta), "shape": list(idx[1].shape), "nnz": idx[1].nnz,
            "load_and_integrity_s": load_s, "first_query_s": durations[0],
            "warm_query_s": durations[1:], "warm_median_s": statistics.median(durations[1:]),
            "warm_max_s": max(durations[1:]), "results": results}


def smoke_more():
    # Import calculators first, location_sim's local import then uses reviewed module.
    sys.modules["calculators"] = load("calculators")
    tariff = load("tariff").calc(100_000_000, "raw_material")
    location = load("location_sim").simulate(100, 5000, 50000)
    assert tariff["total_import_tax_VND"] >= 0 and location
    return {"tariff": tariff, "location": location}


def phase(name):
    start = time.perf_counter()
    result = globals()[name]()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result["metrics"] = {"wall_s": time.perf_counter() - start,
                         "peak_rss_mib": usage.ru_maxrss / 1024,
                         "cpu_user_s": usage.ru_utime, "cpu_system_s": usage.ru_stime}
    write(WORK / f"{name}.json", result)
    print(json.dumps({"phase": name, "metrics": result["metrics"]}), flush=True)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    phases = ["calculators", "refs", "smoke_more", "build", "search", "search"]
    all_results = []
    for i, name in enumerate(phases):
        t = time.perf_counter()
        with (WORK / f"{i}-{name}.txt").open("w", encoding="utf-8") as log:
            p = subprocess.run([sys.executable, __file__, name], stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        record = {"phase": name, "attempt": i, "exit_code": p.returncode,
                  "process_wall_s": time.perf_counter() - t}
        if p.returncode == 0:
            record["result"] = json.loads((WORK / f"{name}.json").read_text())
        all_results.append(record)
        print(json.dumps({k: v for k, v in record.items() if k != "result"}), flush=True)
        if p.returncode:
            break
    versions = {n: importlib.metadata.version(n) for n in
                ("mcp", "Authlib", "fastapi", "numpy", "scipy", "scikit-learn", "beautifulsoup4",
                 "uvicorn", "SQLAlchemy", "alembic", "psycopg")}
    cgroup = {}
    for n in ("memory.max", "memory.peak", "memory.events", "cpu.max", "cpu.stat"):
        p = Path("/sys/fs/cgroup") / n
        cgroup[n] = p.read_text() if p.exists() else None
    report = {"python": sys.version, "platform": platform.platform(), "versions": versions,
              "cpu_count_visible": os.cpu_count(), "cgroup": cgroup,
              "cold_definition": "fresh process, OS page cache not flushed",
              "disk_bytes": {n: (WORK / n).stat().st_size for n in INDEX_FILES if (WORK / n).exists()},
              "phases": all_results, "passed": all(r["exit_code"] == 0 for r in all_results) and len(all_results) == len(phases)}
    write(WORK / "benchmark.json", report)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        phase(sys.argv[1])
    else:
        main()
