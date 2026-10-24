#!/usr/bin/env python3
"""Prepare and run reproducible, evidence-gated DC synthesis. Python >= 3.6."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
DC = ROOT / "hw/dc_syn"
sys.path.insert(0, str(ROOT / "scripts"))
from rtl_gate import read_json, require, verify_export
from report_dc import analyze, write_summary, compact_record

TIME_KEYS = ("period_ns", "clock_latency_ns", "setup_uncertainty_ns", "hold_uncertainty_ns",
             "clock_transition_ns", "input_delay_max_ns", "input_delay_min_ns", "output_delay_max_ns",
             "output_delay_min_ns", "input_transition_ns", "output_load_pf")
BOOL_KEYS = ("clock_gating", "optimize_area", "hold_fix", "write_sdf")
LOCAL_TZ = timezone(timedelta(hours=8))


def utc():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def local_time():
    return datetime.now(LOCAL_TZ)


def default_run_id(top, when=None):
    return "dc_{}_{}".format(top, (when or local_time()).astimezone(LOCAL_TZ).strftime("%m%d%H%M"))


def constraint_defaults(value):
    result = dict(value)
    result.setdefault("clock_gating", True)
    hierarchy = {"keep_modules": ["PE*", "Pe*", "pe_*", "SubPE*", "ProcessingElement*"],
                 "expand_modules": [], "expand_instances": [], "expand_depth": 0}
    hierarchy.update(result.get("hierarchy", {}))
    result["hierarchy"] = hierarchy
    return result


def tcl_string(value):
    # Double-quoted Tcl words, with substitutions disabled, including path metacharacters.
    text = str(int(value)) if isinstance(value, bool) else str(value)
    for old, new in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"), ("[", "\\["),
                     ("]", "\\]"), ("\n", "\\n"), ("\r", "\\r")):
        text = text.replace(old, new)
    return '"' + text + '"'


def run_path(run_id):
    match = re.fullmatch(r"dc_([A-Za-z_][A-Za-z0-9_$]*)_(\d{8})", run_id)
    require(match, "Run ID must be dc_<RTL-top>_<MMDDHHMM>")
    datetime.strptime("2000" + match.group(2), "%Y%m%d%H%M")
    base = DC / "runs"
    path = base / run_id
    require(not base.is_symlink() and not path.is_symlink(), "Symlinked run directory rejected")
    require(path.resolve().parent == base.resolve(), "Run escaped runs/")
    return path


def load_inputs(args):
    gate = verify_export(args.export_id, ROOT)
    tech, constraints, machine = [read_json(p) for p in (args.technology, args.constraints, args.machine)]
    constraints = constraint_defaults(constraints)
    require(all(c.get("schema_version") == 1 for c in (tech, constraints, machine)), "Unsupported schema")
    required = set(TIME_KEYS + BOOL_KEYS + ("schema_version", "constraint_id", "purpose", "clock_port",
                                           "timing_max_paths", "clock_gating_min_bitwidth", "hierarchy"))
    require(set(constraints) == required, "Missing or unknown constraint keys")
    require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", constraints["clock_port"]), "Invalid clock port")
    for key in TIME_KEYS:
        value = constraints[key]
        require(type(value) in (int, float) and math.isfinite(value), "Invalid numeric constraint: " + key)
        if key not in ("input_delay_min_ns", "output_delay_min_ns"):
            require(value >= 0, "Negative constraint: " + key)
    require(constraints["period_ns"] > 0, "Clock period must be positive")
    for prefix in ("input", "output"):
        require(constraints[prefix + "_delay_min_ns"] <= constraints[prefix + "_delay_max_ns"],
                "IO minimum delay exceeds maximum")
    for key in BOOL_KEYS:
        require(type(constraints[key]) is bool, "Expected boolean: " + key)
    for key in ("timing_max_paths", "clock_gating_min_bitwidth"):
        require(type(constraints[key]) is int and constraints[key] > 0, "Expected positive integer: " + key)
    hierarchy = constraints["hierarchy"]
    require(set(hierarchy) == {"keep_modules", "expand_modules", "expand_instances", "expand_depth"},
            "Unknown/missing hierarchy settings")
    require(type(hierarchy["expand_depth"]) is int and hierarchy["expand_depth"] >= 0, "Invalid expansion depth")
    for key in ("keep_modules", "expand_modules", "expand_instances"):
        require(isinstance(hierarchy[key], list) and all(isinstance(p, str) and p and "\n" not in p
                for p in hierarchy[key]), "Hierarchy selectors must be lists of patterns")
    require(tech.get("area_unit") == "um2", "v1 requires documented library area in um2")
    require(tech.get("technology_id") and tech.get("process") and tech.get("pvt") and
            tech.get("operating_condition") and tech.get("wire_load_model"), "Incomplete technology profile")
    libs = tech["target_libraries"]
    require(libs and len(libs) == len(set(libs)) and tech["operating_library"] in libs,
            "Invalid target/operating library selection")
    for lib in libs:
        require(re.fullmatch(r"[A-Za-z0-9_]+", lib), "Invalid library identifier")
    require(set(machine) == {"schema_version", "libraries", "dc_shell", "setup_script"},
            "Missing or unknown machine settings; do not place license credentials here")
    targets = []
    for lib in libs:
        path = Path(machine["libraries"][lib])
        require(path.is_absolute() and path.is_file() and os.access(str(path), os.R_OK),
                "Unreadable explicit library binding: " + lib)
        require(path.name == lib + ".db", "DB filename differs from selected library ID")
        targets.append(str(path.resolve()))
    shell = Path(machine["dc_shell"])
    require(shell.is_absolute() and shell.is_file() and os.access(str(shell), os.X_OK),
            "dc_shell must be an executable absolute path (not launched by check/prepare)")
    if machine["setup_script"]:
        setup = Path(machine["setup_script"])
        require(setup.is_absolute() and setup.is_file(), "Unreadable environment setup script")
    vt = tech.get("multi_vt")
    if vt:
        require(vt["base_library"] in libs and vt["lvt_library"] in libs and
                vt["base_library"] != vt["lvt_library"] and 0 <= vt["max_lvt_percent"] <= 100,
                "Invalid multi-Vt selection")
    return {"schema_version": 2, "gate": gate, "technology": tech, "constraints": constraints,
            "machine": machine, "target_dbs": targets,
            "config_paths": {k: str(getattr(args, k).resolve()) for k in ("technology", "constraints", "machine")}}


def render_tcl(data):
    settings = dict(data["constraints"])
    settings.update({k: data["technology"][k] for k in ("operating_library", "operating_condition", "wire_load_model")})
    settings["top"] = data["gate"]["top"]
    vt = data["technology"].get("multi_vt")
    settings["multi_vt"] = bool(vt)
    if vt:
        settings.update(vt)
    text = "# Generated from explicit JSON settings; do not edit.\n"
    text += "".join("set {} {}\n".format(k, tcl_string(v)) for k, v in settings.items() if k != "hierarchy")
    hierarchy = settings["hierarchy"]
    text += "set expand_depth {}\n".format(hierarchy["expand_depth"])
    for key, values in (("target_dbs", data["target_dbs"]),
                        ("target_library_names", data["technology"]["target_libraries"]),
                        ("rtl_sources", data["gate"]["sources"]), ("include_dirs", data["gate"]["include_dirs"]),
                        ("keep_module_patterns", hierarchy["keep_modules"]),
                        ("expand_module_patterns", hierarchy["expand_modules"]),
                        ("expand_instance_patterns", hierarchy["expand_instances"])):
        text += "set {} [list {}]\n".format(key, " ".join(tcl_string(v) for v in values))
    return text


def prepare(args, data):
    run_id = args.run_id or default_run_id(data["gate"]["top"])
    run = run_path(run_id)
    require(run_id.rsplit("_", 1)[0] == "dc_" + data["gate"]["top"], "Run name must match the RTL top")
    require(not run.exists(), "This top already has a run in this minute; use a different minute, never overwrite")
    run.mkdir(parents=True, exist_ok=False)
    inputs = run / "inputs"
    inputs.mkdir()
    data["created_at"] = local_time().isoformat(timespec="seconds")
    data["purpose"] = args.purpose
    dump(inputs / "resolved.json", data)
    for name in ("DC.tcl", "hierarchy.tcl", "report.md.in"):
        shutil.copyfile(DC / "templates" / name, inputs / name)
    (inputs / "resolved.tcl").write_text(render_tcl(data), encoding="utf-8")
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--run-id", run_id]
    (run / "launch.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\nexec " +
                                  " ".join(shlex.quote(v) for v in command) + "\n", encoding="utf-8")
    dump(run / "state.json", {"phase": "prepared", "run_id": run_id, "created_at": data["created_at"]})
    print("PREPARED {} (DC not launched)".format(run))
    return 0


def verify_inputs(run, for_execution=False):
    data = read_json(run / "inputs/resolved.json")
    gate = verify_export(data["gate"]["export_id"], ROOT)
    require(gate["rtl_fingerprint"] == data["gate"]["rtl_fingerprint"], "RTL directory changed since preparation")
    if for_execution:
        for key, path in data.get("config_paths", {}).items():
            current = read_json(path)
            if key == "constraints":
                current = constraint_defaults(current)
            require(current == data[key], "Configuration changed; prepare a new run: " + key)
        require((run / "inputs/resolved.tcl").read_text() == render_tcl(data), "Prepared Tcl settings changed")
        for path in data["target_dbs"]:
            require(Path(path).is_file() and os.access(path, os.R_OK), "Library is not readable: " + path)
    return data


def exit_status(summary):
    return 2 if not summary["synthesis_valid"] else (0 if summary["timing_pass"] else
           3 if summary["timing_status"] == "FAIL" else 4)


def execute(run):
    data = verify_inputs(run, for_execution=True)
    require(read_json(run / "state.json")["phase"] == "prepared", "Run already started; use a new run")
    lock = run / ".running"
    lock.mkdir(exist_ok=False)
    try:
        dump(run / "state.json", {"phase": "running", "pid": os.getpid(), "started_utc": utc()})
        (run / "logs").mkdir()
        machine = data["machine"]
        # Pass paths as positional arguments; never interpolate configuration into shell code.
        script = 'set -e; if [[ -n "$1" ]]; then source "$1"; fi; cd "$2"; exec "$3" -no_home_init -no_local_init -f inputs/DC.tcl'
        with (run / "logs/dc.stdout.log").open("wb") as out, (run / "logs/dc.stderr.log").open("wb") as err:
            try:
                rc = subprocess.call(["bash", "-c", script, "dc-launch", machine["setup_script"],
                                      str(run), machine["dc_shell"]], cwd=str(run), stdout=out, stderr=err)
            except OSError as error:
                err.write(str(error).encode())
                rc = 127
        (run / "exit_code.txt").write_text(str(rc) + "\n", encoding="utf-8")
        summary = analyze(run, data)
        try:
            verify_inputs(run)
        except (ValueError, OSError, KeyError) as error:
            summary.update(status="invalid", synthesis_valid=False, timing_pass=False, timing_status="UNKNOWN")
            summary["errors"].append("Inputs changed during synthesis: " + str(error))
        summary["finished_utc"] = utc()
        write_summary(run, summary)
        dump(run / "state.json", {"phase": "finished" if summary["synthesis_valid"] else "failed",
                                  "finished_utc": summary["finished_utc"], "exit_status": exit_status(summary)})
        print("{}: synthesis_valid={}, timing={}, area_um2={}".format(
            run.name, summary["synthesis_valid"], summary["timing_status"], summary["area"]["total_cell_area_um2"]))
        return exit_status(summary)
    except BaseException:
        dump(run / "state.json", {"phase": "interrupted", "finished_utc": utc()})
        raise
    finally:
        lock.rmdir()


def report(run, record_name=None):
    require(not (run / ".running").exists(), "Run is active")
    data = verify_inputs(run)
    summary = analyze(run, data)
    if record_name:
        require(Path(record_name).name == record_name and record_name.endswith(".json"), "Record must be a JSON filename")
        require(summary["synthesis_valid"], "Invalid run cannot be published as a synthesis result")
        (DC / "records").mkdir(exist_ok=True)
        dump(DC / "records" / record_name, compact_record(summary))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return exit_status(summary)


def clean(run, apply):
    require(read_json(run / "state.json")["phase"] in ("finished", "failed"),
            "Cleanup requires a terminal run; interrupted runs need process investigation")
    require(not (run / ".running").exists(), "Run is active")
    work = run / "work"
    require(not work.is_symlink(), "Refusing a symlinked work directory")
    paths = list(work.rglob("*")) if work.exists() else []
    require(not any(p.is_symlink() for p in paths), "Refusing cleanup across symlinks")
    size = sum(p.stat().st_size for p in paths if p.is_file())
    print("{}: {} bytes in work/; reports, netlist and evidence retained".format("DELETE" if apply else "PLAN", size))
    if apply:
        if work.exists():
            shutil.rmtree(str(work))
        dump(run / "cleanup.json", {"utc": utc(), "deleted": ["work/"], "bytes": size})
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    for name in ("check", "prepare"):
        sub = commands.add_parser(name, help="Validate inputs" if name == "check" else "Prepare without launching DC")
        sub.add_argument("--export-id", required=True)
        sub.add_argument("--technology", required=True, type=Path)
        sub.add_argument("--constraints", required=True, type=Path)
        sub.add_argument("--machine", required=True, type=Path)
        if name == "prepare":
            sub.add_argument("--run-id")
            sub.add_argument("--purpose", default="RTL 综合面积与时序检查")
    for name in ("run", "report", "clean"):
        sub = commands.add_parser(name)
        sub.add_argument("--run-id", required=True)
        if name == "clean":
            sub.add_argument("--apply", action="store_true", help="Default only prints the deletion plan")
        if name == "report":
            sub.add_argument("--record", help="Write a concise JSON filename in dc_syn/records")
    args = parser.parse_args()
    try:
        if args.command in ("check", "prepare"):
            data = load_inputs(args)
            if args.command == "prepare":
                return prepare(args, data)
            print("CHECKED {}: {} sources; libraries readable; DC not launched".format(args.export_id, len(data["gate"]["sources"])))
            return 0
        if args.command == "run":
            return execute(run_path(args.run_id))
        if args.command == "report":
            return report(run_path(args.run_id), args.record)
        if args.command == "clean":
            return clean(run_path(args.run_id), args.apply)
        parser.print_help()
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("DC flow rejected: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
