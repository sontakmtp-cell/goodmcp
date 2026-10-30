"""Bounded, data-only ZIP inspection. Never extracts, imports, unpickles or fetches URLs."""
from dataclasses import dataclass
import hashlib
import json
import posixpath
import re
import stat
import unicodedata
import zipfile

CHUNK = 8 * 1024 * 1024
MAX_ZIP = 1024 ** 3
MAX_EXPANDED = 3 * 1024 ** 3
MAX_FILES = 10000
MAX_TEXT = 4 * 1024 ** 2
TEXT = {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".html", ".ini", ".toml", ".csv", ".sh"}
MANIFESTS = ("plugin.json", ".codex-plugin/plugin.json", ".codebuddy-plugin/plugin.json")


class InvalidPackage(ValueError): pass


def safe_path(value):
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024:
        raise InvalidPackage("invalid_path")
    if value != unicodedata.normalize("NFC", value) or "\\" in value or ":" in value:
        raise InvalidPackage("unsafe_path")
    if any(ord(c) < 32 or ord(c) == 127 for c in value): raise InvalidPackage("unsafe_path")
    parts = value.split("/")
    for part in parts:
        if not part or part in (".", "..") or part.endswith((" ", ".")):
            raise InvalidPackage("unsafe_path")
        if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", part):
            raise InvalidPackage("unsafe_path")
    return value


def json_data(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise InvalidPackage("duplicate_json_key")
            result[k] = v
        return result
    try: return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as e: raise InvalidPackage("invalid_json") from e


def tree_hash(files):
    """Versioned portable identity: UTF-8 path byte ordering, LF, no host Path ordering."""
    return hashlib.sha256(b"goodmcp-tree-v1\n" + b"".join(
        p.encode("utf-8") + b"\0" + files[p]["sha256"].encode() + b"\0" + str(files[p]["bytes"]).encode() + b"\n"
        for p in sorted(files, key=lambda s: s.encode("utf-8")))).hexdigest()


def secret_check(path, block):
    if path.rsplit("/", 1)[-1].lower() in (".env", "id_rsa", "id_ed25519", "credentials", ".netrc"):
        raise InvalidPackage("secret_file")
    if re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b", block):
        raise InvalidPackage("secret_detected")


@dataclass
class Scan:
    manifest: dict
    files: dict
    texts: dict
    skills: list
    agents: list
    warnings: list
    root: str
    tree_sha256: str

    def preview(self):
        return {"name": self.manifest["name"], "manifest_version": self.manifest["version"],
            "license": self.manifest.get("license", "unknown"), "tree_sha256": self.tree_sha256,
            "tree_hash_format": "goodmcp-tree-v1", "root_prefix": self.root,
            "files": len(self.files), "bytes": sum(f["bytes"] for f in self.files.values()),
            "skills": [{"name": x["name"], "path": x["path"]} for x in self.skills],
            "agents": [{"name": x["name"], "path": x["path"]} for x in self.agents],
            "roles": len(self.skills) + len(self.agents), "warnings": self.warnings[:100],
            "warning_count": len(self.warnings), "python_files": sum(p.endswith(".py") for p in self.files),
            "runtime": "source_only_no_execution", "pdf_files": sum(p.lower().endswith(".pdf") for p in self.files),
            "quarantined_files": sum(f.get("quarantined", False) for f in self.files.values()),
            "pdf_indexed": False}


def scan_zip(source):
    try:
        with zipfile.ZipFile(source) as z:
            entries, seen, total = [], set(), 0
            if len(z.infolist()) > MAX_FILES * 2: raise InvalidPackage("too_many_entries")
            for info in z.infolist():
                # orig_filename preserves NULs which ZipInfo.filename otherwise truncates.
                path = safe_path(info.orig_filename.rstrip("/"))
                key = path.casefold()
                if key in seen: raise InvalidPackage("duplicate_path")
                seen.add(key)
                mode = info.external_attr >> 16
                if stat.S_IFMT(mode) not in (0, stat.S_IFDIR, stat.S_IFREG): raise InvalidPackage("special_file")
                if info.flag_bits & 1: raise InvalidPackage("encrypted_zip")
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED): raise InvalidPackage("compression_not_supported")
                if info.is_dir(): continue
                if stat.S_ISDIR(mode): raise InvalidPackage("invalid_directory")
                total += info.file_size
                if info.file_size > MAX_ZIP or total > MAX_EXPANDED: raise InvalidPackage("expanded_limit")
                if info.file_size > max(1, info.compress_size) * 200: raise InvalidPackage("compression_ratio")
                entries.append((path, info))
            if not entries or len(entries) > MAX_FILES: raise InvalidPackage("file_count")
            paths = {p for p, _ in entries}
            folded_files = {p.casefold() for p in paths}
            if any("/".join(p.split("/")[:i]).casefold() in folded_files for p in paths for i in range(1, len(p.split("/")))):
                raise InvalidPackage("file_directory_collision")
            roots = {p[:-len(m)] for p in paths for m in MANIFESTS if p == m or p.endswith("/" + m)}
            # Overlays are relative to the same root, not separate nested plugins.
            roots = {r for r in roots if not r.endswith((".codex-plugin/", ".codebuddy-plugin/"))}
            if len(roots) != 1: raise InvalidPackage("ambiguous_plugin_root")
            root = roots.pop()
            if any(not p.startswith(root) for p in paths): raise InvalidPackage("files_outside_plugin_root")
            files, texts, quarantine, text_bytes = {}, {}, [], 0
            for original, info in entries:
                p = original[len(root):]
                secret_check(p, b"")
                h, count, keep, tail, blocked = hashlib.sha256(), 0, bytearray(), b"", False
                with z.open(info) as stream:
                    while block := stream.read(1024 * 1024):
                        count += len(block)
                        if count > info.file_size or count > MAX_ZIP: raise InvalidPackage("expanded_limit")
                        h.update(block)
                        try: secret_check(p, tail + block)
                        except InvalidPackage as exc:
                            # Captured web pages remain private source, never active resources.
                            # The generic policy applies to any plugin, not an allowlist by name.
                            if str(exc) != "secret_detected" or not p.lower().endswith(".html"): raise
                            blocked = True
                        tail = block[-256:]
                        if info.file_size <= MAX_TEXT and (p.endswith(".md") or p.rsplit("/", 1)[-1] in ("plugin.json", "MANIFEST.json")): keep.extend(block)
                if count != info.file_size: raise InvalidPackage("zip_size_mismatch")
                active = "_backup_zh" not in p.split("/") and not blocked
                files[p] = {"sha256": h.hexdigest(), "bytes": count, "active": active, "zip_path": original, "quarantined": blocked}
                if blocked: quarantine.append({"code": "embedded_credential_html_quarantined", "source": p})
                if keep:
                    text_bytes += len(keep)
                    if text_bytes > 16 * 1024 * 1024: raise InvalidPackage("catalog_text_limit")
                    try: texts[p] = keep.decode("utf-8-sig")
                    except UnicodeError: pass
            manifests = [(p, json_data(texts[p])) for p in MANIFESTS if p in texts]
            if not manifests: raise InvalidPackage("manifest_missing_or_too_large")
            manifest = {}
            for path, data in manifests:
                if not isinstance(data, dict): raise InvalidPackage("invalid_manifest")
                for key in ("name", "version", "description", "license", "author", "skills", "agents"):
                    if key not in data: continue
                    if key in manifest and manifest[key] != data[key]: raise InvalidPackage("manifest_conflict")
                    manifest[key] = data[key]
                # Interface is presented separately, and must agree across root/overlay.
                interface = data.get("interface", data.get("extensions", {}).get("com.openai", {}).get("interface"))
                if interface is not None:
                    if "interface" in manifest and manifest["interface"] != interface: raise InvalidPackage("manifest_conflict")
                    manifest["interface"] = interface
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", str(manifest.get("name", ""))): raise InvalidPackage("invalid_plugin_name")
            if not isinstance(manifest.get("version"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,99}", manifest["version"]):
                raise InvalidPackage("invalid_version")
            skills, agents, warnings = [], [], list(quarantine)
            for kind, default, result in (("skills", "skills/", skills), ("agents", "agents/", agents)):
                selected = manifest.get(kind, default)
                if isinstance(selected, str): selected = [selected]
                if not isinstance(selected, list) or len(selected) > 1000: raise InvalidPackage("invalid_entrypoints")
                candidates = set()
                for entry in selected:
                    if not isinstance(entry, str): raise InvalidPackage("invalid_entrypoints")
                    entry = entry.removeprefix("./").rstrip("/")
                    safe_path(entry)
                    hits = [p for p in files if p == entry or p.startswith(entry + "/")]
                    if not hits and kind in manifest: raise InvalidPackage("missing_entrypoint")
                    for p in hits:
                        if not files[p]["active"]: continue
                        if (kind == "skills" and p.endswith("/SKILL.md")) or (kind == "agents" and p.endswith(".md")):
                            candidates.add(p)
                names = set()
                if len(candidates) > 100: raise InvalidPackage("role_count_limit")
                for p in sorted(candidates):
                    body = texts.get(p)
                    if not body or not body.startswith("---\n") and not body.startswith("---\r\n"): raise InvalidPackage("invalid_role_document")
                    sections = body.split("---", 2)
                    if len(sections) != 3: raise InvalidPackage("invalid_role_document")
                    front = sections[1]
                    match = re.search(r"(?m)^name:\s*([a-z0-9_-]+)\s*$", front)
                    if not match or match[1] in names: raise InvalidPackage("invalid_or_duplicate_role")
                    names.add(match[1])
                    result.append({"name": match[1], "path": p, "body": body})
            if not skills and not agents: raise InvalidPackage("no_roles")
            # Missing local prose links are diagnostics: source documents are kept verbatim.
            for p, body in texts.items():
                if not p.endswith(".md") or not files[p]["active"]: continue
                for i, match in enumerate(re.finditer(r"\]\(([^\s)]+)\)", body)):
                    if i >= 1000: raise InvalidPackage("document_reference_limit")
                    link = match[1]
                    if ":" in link or link.startswith("#"): continue
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(p), link.split("#")[0]))
                    if target not in files: warnings.append({"code": "missing_document_reference", "source": p, "target": target})
            for p, body in texts.items():
                if p.rsplit("/", 1)[-1] != "MANIFEST.json": continue
                data = json_data(body)
                if not isinstance(data, dict) or not isinstance(data.get("files"), list): continue
                if len(data["files"]) > MAX_FILES: raise InvalidPackage("manifest_reference_limit")
                for item in data["files"]:
                    if not isinstance(item, dict) or not isinstance(item.get("filename"), str): continue
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(p), item["filename"]))
                    if target not in files: warnings.append({"code": "source_manifest_missing", "target": target})
                    elif files[target]["bytes"] != item.get("size_bytes"):
                        warnings.append({"code": "source_manifest_size_mismatch", "target": target})
            if any(p.endswith((".pkl", ".pickle", ".npz")) for p in files): warnings.append({"code": "supplied_index_untrusted_not_loaded"})
            if any(p.endswith(".py") for p in files): warnings.append({"code": "python_source_only_g4_required"})
            if manifest.get("license") is None: warnings.append({"code": "license_unknown_private_only"})
            if any(not f["active"] for f in files.values()): warnings.append({"code": "backup_preserved_inactive"})
            return Scan(manifest, files, texts, skills, agents, warnings, root, tree_hash(files))
    except InvalidPackage: raise
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise InvalidPackage("invalid_zip_or_manifest") from exc
