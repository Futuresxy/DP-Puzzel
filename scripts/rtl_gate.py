#!/usr/bin/env python3
"""Read-only RTL evidence gate shared by synthesis and future power tools (v1)."""
import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EXPORT_ID = r"[A-Za-z_][A-Za-z0-9_]*__[A-Za-z0-9_.-]+__\d{8}T\d{12}Z__[0-9a-f]{12}"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def contained(base, name):
    """Reject absolute names, traversal, and symlinks escaping the owned tree."""
    name = Path(name)
    if name.is_absolute() or ".." in name.parts or not name.parts:
        raise ValueError("Expected a relative path: {}".format(name))
    path = (base / name).resolve(strict=True)
    if base.resolve() not in path.parents:
        raise ValueError("Path escapes {}: {}".format(base, name))
    return path


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_export(export_id, root=ROOT):
    """Check existing evidence; never create, upgrade, or sign a PASS record."""
    root = Path(root).resolve()
    require(re.fullmatch(EXPORT_ID, export_id), "Invalid explicit export ID")
    export = contained(root / "hw/rtl", export_id)
    manifest_path = contained(export, "manifest.json")
    manifest = read_json(manifest_path)
    require(manifest.get("schema_version") == 1, "Unsupported RTL manifest schema")
    require(manifest.get("export_id") == export_id, "Export ID mismatch")
    require(manifest.get("status") == "passed", "RTL export is not passed")
    top = manifest.get("top", "")
    require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", top), "Invalid top module")
    mapping = manifest.get("module_map", {})
    require(top in mapping and all(isinstance(v, dict) and v.get("source_file") and
            ((v.get("source_language", "chisel") == "chisel" and v.get("chisel_class")) or
             (v.get("source_language") == "systemverilog" and v.get("chisel_class") is None))
            for v in mapping.values()), "Missing module/source mapping")
    contained(export, "README.md")
    filelist = contained(export, "files.f")
    entries = manifest.get("files", [])
    require(entries, "Empty RTL manifest")
    payload = {}
    sources = []
    tracked = [manifest_path, filelist, export / "README.md"]
    for entry in entries:
        name = entry["path"]
        require(name not in payload, "Duplicate RTL file")
        path = contained(export, name)
        require(Path(name).parts[0] == "src", "RTL payload must be under src/")
        require(entry.get("role") in ("source", "header"), "Unsupported RTL file role")
        require(sha256(path) == entry["sha256"], "RTL hash mismatch: " + name)
        payload[name] = entry["sha256"]
        tracked.append(path)
        if entry["role"] == "source":
            require(path.suffix in (".sv", ".v"), "Expected Verilog/SystemVerilog")
            sources.append(name)
    listed = [line.strip() for line in filelist.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.lstrip().startswith(("#", "//"))]
    require(listed == sources and sources, "files.f must exactly match ordered source entries")
    # Handwritten SV is an explicit, byte-identical source type, never a fake
    # Chisel class. Its source is also an input to every downstream analysis.
    for item in mapping.values():
        if item.get("source_language") == "systemverilog":
            source = contained(root, item["source_file"])
            source_hash = sha256(source)
            require(source_hash == item.get("source_sha256"), "Stale SystemVerilog source")
            require(item.get("rtl_file") in sources and payload[item["rtl_file"]] == source_hash,
                    "Handwritten SystemVerilog must be exported byte-for-byte")
            tracked.append(source)
    # Prevent analysis of an untracked include; v1 supports self-contained exports only.
    actual = {p.relative_to(export).as_posix() for p in (export / "src").rglob("*") if p.is_file()}
    require(actual == set(payload), "Unlisted or missing files under src/")
    include_dirs = sorted({(export / name).parent for name in payload})
    for name in payload:
        source = (export / name).read_text(encoding="utf-8")
        source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
        for directive in re.findall(r"`include\s+([^\n]+)", source):
            literal = re.fullmatch(r'"([^"\n]+)"\s*', directive.strip())
            require(literal, "v1 requires literal, export-local includes")
            include = Path(literal.group(1))
            require(not include.is_absolute() and ".." not in include.parts, "External include rejected")
            candidates = [(directory / include).resolve() for directory in [(export / name).parent] + include_dirs]
            matches = {p for p in candidates if p.is_file()}
            require(len(matches) == 1 and matches <= {(export / n).resolve() for n in payload},
                    "Missing, ambiguous or untracked include: " + str(include))
    evidence_ref = manifest["verification"]
    evidence_path = contained(root, evidence_ref["path"])
    require(root / "hw/test/runs" in evidence_path.parents, "Evidence must be in hw/test/runs")
    require(sha256(evidence_path) == evidence_ref["sha256"], "Verification receipt hash mismatch")
    evidence = read_json(evidence_path)
    require(evidence.get("schema_version") == 1 and evidence.get("status") == "passed",
            "Missing passed RTL verification")
    require(evidence.get("export_id") == export_id and evidence.get("rtl_sha256") == payload,
            "Verification does not cover this exact RTL")
    require(evidence.get("files_f_sha256") == sha256(filelist), "Verified filelist mismatch")
    require(evidence.get("method") == "systemverilog_testbench" and
            evidence.get("numerical_pass") is True and evidence.get("protocol_pass") is True,
            "Numerical and cycle-protocol RTL verification is required")
    require(evidence.get("verification_id") and evidence.get("command") and
            evidence.get("numeric_semantics") and evidence.get("coverage_matrix") and
            evidence.get("seeds") and evidence.get("simulator", {}).get("version"),
            "Incomplete verification provenance")
    roles = set()
    for entry in evidence.get("inputs", []):
        path = contained(root, entry["path"])
        require(sha256(path) == entry["sha256"], "Stale verification input: " + entry["path"])
        roles.add(entry["role"])
        tracked.append(path)
    require({"testbench", "reference", "vectors", "log"} <= roles,
            "Verification requires hashed testbench, reference, vectors and log")
    tracked.append(evidence_path)
    return {"export_id": export_id, "top": top, "export_dir": str(export),
            "sources": [str(export / name) for name in sources],
            "include_dirs": [str(p) for p in include_dirs],
            "verification_id": evidence["verification_id"],
            "tracked": {str(p): sha256(p) for p in tracked}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_id")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_export(args.export_id), indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, "RTL gate rejected: {}\n".format(error))


if __name__ == "__main__":
    main()
