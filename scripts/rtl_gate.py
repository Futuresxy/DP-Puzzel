#!/usr/bin/env python3
"""Read-only RTL gate: one directory fingerprint plus real regression evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EXPORT_ID = r"[A-Za-z_][A-Za-z0-9_]*__[A-Za-z0-9_.-]+__\d{8}T\d{12}Z__[0-9a-f]{12}"


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def contained(base, name):
    name = Path(name)
    require(not name.is_absolute() and ".." not in name.parts and name.parts,
            "Expected a relative path: " + str(name))
    path = (base / name).resolve(strict=True)
    require(base.resolve() in path.parents, "Path escapes " + str(base))
    return path


def rtl_fingerprint(export):
    """Hash relative names + bytes of files.f and src/, once for the whole RTL.

    manifest/README are metadata and excluded to avoid a self-referential hash.
    Absolute directory names and timestamps do not affect the fingerprint.
    """
    export = Path(export)
    require(not (export / "src").is_symlink(), "Symlinked RTL directory rejected")
    children = list((export / "src").rglob("*"))
    require(not any(p.is_symlink() for p in children), "Symlinked RTL payload rejected")
    files = [export / "files.f"] + sorted(p for p in children if p.is_file())
    digest = hashlib.sha256()
    for path in files:
        name = path.relative_to(export).as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def verify_export(export_id, root=ROOT):
    root = Path(root).resolve()
    require(re.fullmatch(EXPORT_ID, export_id), "Invalid explicit export ID")
    export = contained(root / "hw/rtl", export_id)
    manifest = read_json(contained(export, "manifest.json"))
    require(manifest.get("schema_version") == 2, "RTL manifest requires directory-fingerprint schema v2")
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
    names, sources = [], []
    for entry in entries:
        name = entry["path"]
        path = contained(export, name)
        require(name not in names and Path(name).parts[0] == "src", "Invalid/duplicate RTL path")
        require(entry.get("role") in ("source", "header"), "Unsupported RTL file role")
        names.append(name)
        if entry["role"] == "source":
            require(path.suffix in (".sv", ".v"), "Expected Verilog/SystemVerilog")
            sources.append(name)
    listed = [line.strip() for line in filelist.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.lstrip().startswith(("#", "//"))]
    require(listed == sources and sources, "files.f must exactly match ordered source entries")
    actual = {p.relative_to(export).as_posix() for p in (export / "src").rglob("*") if p.is_file()}
    require(actual == set(names), "Unlisted or missing files under src/")
    fingerprint = rtl_fingerprint(export)
    require(fingerprint == manifest.get("rtl_fingerprint"), "RTL directory fingerprint mismatch")
    for item in mapping.values():
        if item.get("source_language") == "systemverilog":
            source = contained(root, item["source_file"])
            require(item.get("rtl_file") in sources and
                    source.read_bytes() == (export / item["rtl_file"]).read_bytes(),
                    "Handwritten SystemVerilog must be exported byte-for-byte")
    include_dirs = sorted({(export / name).parent for name in names})
    for name in names:
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", (export / name).read_text(encoding="utf-8"), flags=re.S)
        for directive in re.findall(r"`include\s+([^\n]+)", text):
            literal = re.fullmatch(r'"([^"\n]+)"\s*', directive.strip())
            require(literal, "Only literal, export-local includes are supported")
            include = Path(literal.group(1))
            require(not include.is_absolute() and ".." not in include.parts, "External include rejected")
            matches = {(directory / include).resolve() for directory in [(export / name).parent] + include_dirs
                       if (directory / include).is_file()}
            require(len(matches) == 1 and matches <= {(export / n).resolve() for n in names},
                    "Missing, ambiguous or untracked include")
    evidence_path = contained(root, manifest["verification"]["path"])
    require(root / "hw/test/runs" in evidence_path.parents, "Evidence must be in hw/test/runs")
    evidence = read_json(evidence_path)
    require(evidence.get("schema_version") == 2 and evidence.get("status") == "passed",
            "Missing passed RTL verification")
    require(evidence.get("export_id") == export_id and evidence.get("rtl_fingerprint") == fingerprint,
            "Verification does not cover this RTL directory")
    require(evidence.get("method") == "systemverilog_testbench" and evidence.get("numerical_pass") is True and
            evidence.get("protocol_pass") is True, "Numerical and cycle-protocol RTL verification is required")
    require(evidence.get("verification_id") and evidence.get("command") and evidence.get("numeric_semantics") and
            evidence.get("coverage_matrix") and evidence.get("seeds") and evidence.get("simulator", {}).get("version"),
            "Incomplete verification provenance")
    finished = datetime.strptime(evidence["finished_utc"], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc).timestamp()
    roles = set()
    for entry in evidence.get("inputs", []):
        path = contained(root, entry["path"])
        roles.add(entry["role"])
        if entry["role"] in ("testbench", "reference", "vectors"):
            require(path.stat().st_mtime <= finished + 0.001, "Verification input changed; rerun: " + entry["path"])
    require({"testbench", "reference", "vectors", "log"} <= roles, "Missing verification input/log paths")
    return {"export_id": export_id, "top": top, "export_dir": str(export), "rtl_fingerprint": fingerprint,
            "sources": [str(export / n) for n in sources], "include_dirs": [str(p) for p in include_dirs],
            "verification_id": evidence["verification_id"]}


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
