"""Approved-source loader. No arbitrary modules, paths or supplied pickle."""
import hashlib
import importlib.util
import json
from pathlib import Path

PLUGIN = Path("/plugins/vietnam-finance-tax-expert")
CORPUS = PLUGIN / "references/corpus/vietnam-finance-tax-corpus"
WORK = Path("/work")
INDEX_FILES = ("tfidf_vectorizer.pkl", "tfidf_matrix.npz", "chunks_metadata.json", "chunks_full.jsonl")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(name):
    approved = json.loads(Path("/app/reviewed-source.json").read_text())
    rel = approved[name]["path"]
    path = PLUGIN / rel
    if digest(path) != approved[name]["sha256"]:
        raise ValueError(f"Reviewed source hash mismatch: {name}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verified_search():
    # Only the fixed, freshly rebuilt local artifact namespace is accepted.
    manifest = json.loads((WORK / "trusted-index.json").read_text())
    assert manifest["builder_sha256"] == json.loads(Path("/app/reviewed-source.json").read_text())["build_index"]["sha256"]
    for name in INDEX_FILES:
        if digest(WORK / name) != manifest["sha256"][name]:
            raise ValueError(f"Index integrity mismatch: {name}")
    module = load("search_corpus")
    module.VECTORIZER_PATH = WORK / "tfidf_vectorizer.pkl"
    module.MATRIX_PATH = WORK / "tfidf_matrix.npz"
    module.META_PATH = WORK / "chunks_metadata.json"
    return module
