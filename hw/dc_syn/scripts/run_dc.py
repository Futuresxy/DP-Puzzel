#!/usr/bin/env python3
"""Prepare and run reproducible, evidence-gated DC synthesis. Python >= 3.6."""
import argparse
from datetime import datetime, timezone
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
from rtl_gate import read_json, require, sha256, verify_export
from report_dc import analyze, write_summary

TIME_KEYS = ("period_ns", "clock_latency_ns", "setup_uncertainty_ns", "hold_uncertainty_ns",
             "clock_transition_ns", "input_delay_max_ns", "input_delay_min_ns", "output_delay_max_ns",
             "output_delay_min_ns", "input_transition_ns", "output_load_pf")
BOOL_KEYS = ("clock_gating", "optimize_area", "hold_fix", "preserve_hierarchy", "write_sdf")


def utc():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git_output(*args):
    process = subprocess.run(["git", "-C", str(ROOT)] + list(args), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    return process.stdout if process.returncode == 0 else b""


def tcl_string(value):
    # Double-quoted Tcl words, with substitutions disabled, including path metacharacters.
    text = str(int(value)) if isinstance(value, bool) else str(value)
    for old, new in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"), ("[", "\\["),
                     ("]", "\\]"), ("\n", "\\n"), ("\r", "\\r")):
        text = text.replace(old, new)
    return '"' + text + '"'


def run_path(run_id):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id) and run_id not in (".", ".."),
            "Run ID must be a simple relative name")
    base = DC / "runs"
    path = base / run_id
    require(not base.is_symlink() and not path.is_symlink(), "Symlinked run directory rejected")
    require(path.resolve().parent == base.resolve(), "Run escaped runs/")
    return path


def load_inputs(args):
    gate = verify_export(args.export_id, ROOT)
    tech, constraints, machine = [read_json(p) for p in (args.technology, args.constraints, args.machine)]
    require(all(c.get("schema_version") == 1 for c in (tech, constraints, machine)), "Unsupported schema")
    required = set(TIME_KEYS + BOOL_KEYS + ("schema_version", "constraint_id", "purpose", "clock_port",
                                           "timing_max_paths", "clock_gating_min_bitwidth"))
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
    tracked = dict(gate["tracked"])
    for lib in libs:
        path = Path(machine["libraries"][lib])
        require(path.is_absolute() and path.is_file() and os.access(str(path), os.R_OK),
                "Unreadable explicit library binding: " + lib)
        require(path.name == lib + ".db", "DB filename differs from selected library ID")
        targets.append(str(path.resolve()))
        tracked[str(path.resolve())] = sha256(path)
    shell = Path(machine["dc_shell"])
    require(shell.is_absolute() and shell.is_file() and os.access(str(shell), os.X_OK),
            "dc_shell must be an executable absolute path (not launched by check/prepare)")
    tracked[str(shell.resolve())] = sha256(shell)
    if machine["setup_script"]:
        setup = Path(machine["setup_script"])
        require(setup.is_absolute() and setup.is_file(), "Unreadable environment setup script")
        tracked[str(setup.resolve())] = sha256(setup)
    vt = tech.get("multi_vt")
    if vt:
        require(vt["base_library"] in libs and vt["lvt_library"] in libs and
                vt["base_library"] != vt["lvt_library"] and 0 <= vt["max_lvt_percent"] <= 100,
                "Invalid multi-Vt selection")
    for path in (args.technology, args.constraints, args.machine, Path(__file__),
                 DC / "scripts/report_dc.py", ROOT / "scripts/rtl_gate.py",
                 DC / "templates/DC.tcl", DC / "templates/report.md.in"):
        tracked[str(path.resolve())] = sha256(path)
    return {"schema_version": 1, "gate": gate, "technology": tech, "constraints": constraints,
            "machine": machine, "target_dbs": targets, "input_hashes": tracked}


def prepare(args, data):
    import hashlib
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    run_id = args.run_id or "{}__{}__{}".format(data["gate"]["top"], utc(), fingerprint)
    run = run_path(run_id)
    require(not run.exists(), "Run exists; prepare a new run instead of overwriting")
    run.mkdir(parents=True, exist_ok=False)
    inputs = run / "inputs"
    inputs.mkdir()
    data["source"] = {"commit": git_output("rev-parse", "HEAD").decode().strip() or None,
                      "tracked_diff_sha256": hashlib.sha256(git_output("diff", "HEAD", "--")).hexdigest(),
                      "automation_inputs": "inputs/hashes.json"}
    data["created_utc"] = utc()
    dump(inputs / "resolved.json", data)
    shutil.copyfile(DC / "templates/DC.tcl", inputs / "DC.tcl")
    shutil.copyfile(DC / "templates/report.md.in", inputs / "report.md.in")
    settings = dict(data["constraints"])
    settings.update({k: data["technology"][k] for k in ("operating_library", "operating_condition", "wire_load_model")})
    settings["top"] = data["gate"]["top"]
    vt = data["technology"].get("multi_vt")
    settings["multi_vt"] = bool(vt)
    if vt:
        settings.update(vt)
    text = "# Generated from explicit JSON settings; do not edit.\n"
    text += "".join("set {} {}\n".format(k, tcl_string(v)) for k, v in settings.items())
    for key, values in (("target_dbs", data["target_dbs"]),
                        ("target_library_names", data["technology"]["target_libraries"]),
                        ("rtl_sources", data["gate"]["sources"]), ("include_dirs", data["gate"]["include_dirs"])):
        text += "set {} [list {}]\n".format(key, " ".join(tcl_string(v) for v in values))
    (inputs / "resolved.tcl").write_text(text, encoding="utf-8")
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--run-id", run_id]
    (run / "launch.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\nexec " +
                                  " ".join(shlex.quote(v) for v in command) + "\n", encoding="utf-8")
    hashes = dict(data["input_hashes"])
    for path in list(inputs.iterdir()) + [run / "launch.sh"]:
        hashes[str(path)] = sha256(path)
    dump(inputs / "hashes.json", hashes)
    dump(run / "state.json", {"phase": "prepared", "run_id": run_id, "created_utc": data["created_utc"]})
    print("PREPARED {} (DC not launched)".format(run))
    return 0


def verify_inputs(run):
    for path, expected in read_json(run / "inputs/hashes.json").items():
        require(Path(path).is_file() and sha256(path) == expected, "Changed/missing input: " + path)
    data = read_json(run / "inputs/resolved.json")
    verify_export(data["gate"]["export_id"], ROOT)
    return data


def exit_status(summary):
    return 2 if not summary["synthesis_valid"] else (0 if summary["timing_pass"] else
           3 if summary["timing_status"] == "FAIL" else 4)


def execute(run):
    data = verify_inputs(run)
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
        outputs = [p for directory in ("reports", "netlist", "logs")
                   for p in (run / directory).rglob("*") if p.is_file()]
        outputs += [run / name for name in ("exit_code.txt", "DC_COMPLETE", "summary.json", "summary.csv", "REPORT.md")
                    if (run / name).is_file()]
        dump(run / "outputs.sha256.json", {str(p.relative_to(run)): sha256(p) for p in outputs})
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


def report(run):
    require(not (run / ".running").exists(), "Run is active")
    data = verify_inputs(run)
    for name, expected in read_json(run / "outputs.sha256.json").items():
        path = run / name
        require(path.is_file() and sha256(path) == expected, "Output hash mismatch: " + name)
    summary = analyze(run, data)
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
    for name in ("run", "report", "clean"):
        sub = commands.add_parser(name)
        sub.add_argument("--run-id", required=True)
        if name == "clean":
            sub.add_argument("--apply", action="store_true", help="Default only prints the deletion plan")
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
            return report(run_path(args.run_id))
        if args.command == "clean":
            return clean(run_path(args.run_id), args.apply)
        parser.print_help()
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("DC flow rejected: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
