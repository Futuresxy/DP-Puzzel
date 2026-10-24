#!/usr/bin/env python3
"""Check a specific Full export's integrity and instance hierarchy, without simulation."""

import argparse
import hashlib
import json
from pathlib import Path
import re


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message="Invalid Full export"):
    if not condition:
        raise ValueError(message)


def check(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest['export_id'] == directory.name, 'Export ID mismatch')
    require(manifest['state'] == 'generated', 'Expected an unvalidated generated export')
    require(manifest['validation'] == {'rtl_test': 'not_run', 'ppa_eligible': False})
    config = manifest["parameters"]
    count = config["mid_groups"]
    require(1 <= count <= 4)
    require(40 <= config['align_width'] <= 64)
    source_list = "\n".join(f'{f["path"]} {f["sha256"]}' for f in manifest["sources"])
    require(sha256(source_list.encode()) == manifest['source_sha256'], 'Source inventory hash mismatch')
    listed = {}
    for item in manifest["files"]:
        relative = Path(item["path"])
        require(not relative.is_absolute() and '..' not in relative.parts)
        data = (directory / relative).read_bytes()
        require(sha256(data) == item['sha256'], f'File hash mismatch: {relative}')
        require(item['path'] not in listed, f'Duplicate file: {relative}')
        listed[item["path"]] = data
    filelist = (directory / "files.f").read_bytes()
    require(sha256(filelist) == manifest['filelist_sha256'], 'files.f hash mismatch')
    compile_files = [line for line in filelist.decode().splitlines() if not line.startswith("+incdir+")]
    require(len(compile_files) == len(set(compile_files)), 'Duplicate files.f entry')
    require(set(compile_files) == {name for name in listed if name.endswith('.sv')})
    modules = {}
    for item in manifest["modules"]:
        data = listed[item["path"]]
        require(sha256(data) == item['sha256'])
        text = data.decode()
        names = re.findall(r"^\s*module\s+([\w$]+)\b", text, re.M)
        require(names == [item['module']] and Path(item['path']).stem == names[0])
        require(names[0] not in modules, 'Duplicate module definition')
        require(item['chisel_source'].startswith('hw/chisel_src/'))
        require(item['chisel_class'].startswith('dp.'))
        modules[names[0]] = text
    require(len(modules) == 12, 'Full baseline expects twelve concrete module definitions')
    top = manifest["top"]
    require(top in modules)

    def instances(module, prefix):
        return re.findall(r"^\s*(" + re.escape(prefix) + r"\w*)\s+(\w+)\s*\(", modules[module], re.M)

    mid_instances = instances(top, "MidGroupFull_")
    require(len(mid_instances) == count, 'PETile must retain all configured MidGroups')
    for mid_type, _ in mid_instances:
        group_instances = instances(mid_type, "PEGroupFull_")
        require(len(group_instances) == 4, 'Each MidGroup must retain four PEGroups')
        for group_type, _ in group_instances:
            require(len(instances(group_type, 'SubPE_')) == 4, 'Each PEGroup must retain four SubPEs')
    for helper in ("CUnpacker", "LzdNormalize", "RoundPack"):
        require(len(instances(top, helper)) == 1, f'PETile must share one {helper}')
    return {
        "check": "export_integrity_and_hierarchy",
        "export_id": directory.name,
        "source_sha256": manifest["source_sha256"],
        "module_definitions": len(modules),
        "physical_instances": {"PETile": 1, "MidGroupFull": count, "PEGroupFull": 4 * count, "SubPE": 16 * count},
        "rtl_numerical_test": "not_run",
        "ppa_eligible": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_id", help="Explicit directory ID under hw/rtl; never selects the latest export")
    args = parser.parse_args()
    require(Path(args.export_id).name == args.export_id, 'Expected one export ID')
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(check(root / "hw" / "rtl" / args.export_id), indent=2))


if __name__ == "__main__":
    main()
