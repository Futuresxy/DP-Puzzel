#!/usr/bin/env python3
"""Export, RTL-verify, and optionally synthesize the minimal BF16 DC example."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from rtl_gate import contained, read_json, require, sha256, verify_export

ROOT = Path(__file__).resolve().parents[1]
CONFIG = "hw/configs/bf16_sign_pipe_example.json"


def utc():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def dump(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def command_output(command):
    result = subprocess.run(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    require(result.returncode == 0, "Command failed: " + " ".join(command))
    return result.stdout.decode(errors="replace")


def logged(command, cwd, path):
    with path.open("w", encoding="utf-8") as output:
        return subprocess.call(command, cwd=str(cwd), stdout=output, stderr=subprocess.STDOUT)


def export_example():
    config = read_json(ROOT / CONFIG)
    require(config["top"] == "Bf16SignPipe" and config["schema_version"] == 1, "Unsupported example config")
    names = [CONFIG, config["source_template"], config["spec"], config["testbench"], config["reference"],
             "scripts/dc_example.py", "scripts/rtl_gate.py"]
    inputs = {name: sha256(contained(ROOT, name)) for name in names}
    fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    export_id = "{}__{}__{}__{}".format(config["top"], config["config_id"], utc(), fingerprint[:12])
    export = ROOT / "hw/rtl" / export_id
    (export / "src").mkdir(parents=True, exist_ok=False)
    rtl_name = "src/" + config["top"] + ".sv"
    shutil.copyfile(str(ROOT / config["source_template"]), str(export / rtl_name))
    (export / "files.f").write_text(rtl_name + "\n", encoding="utf-8")
    commit = command_output(["git", "rev-parse", "HEAD"]).strip()
    manifest = {"schema_version": 1, "export_id": export_id, "top": config["top"], "status": "generated",
                "created_utc": utc(), "config_path": CONFIG, "parameters": config["parameters"],
                "source_commit": commit, "source_fingerprint_sha256": fingerprint, "source_inputs": inputs,
                "exporter": {"command": [sys.executable, "scripts/dc_example.py", "export"],
                             "python": sys.version.split()[0], "kind": "byte_identical_systemverilog"},
                "module_map": {config["top"]: {"source_language": "systemverilog", "chisel_class": None,
                    "source_file": config["source_template"], "source_sha256": inputs[config["source_template"]],
                    "rtl_file": rtl_name}},
                "files": [{"path": rtl_name, "role": "source", "sha256": sha256(export / rtl_name)}]}
    dump(export / "manifest.json", manifest)
    (export / "README.md").write_text(
        "# {}\n\nStatus: generated (RTL simulation not yet run).\n\n"
        "Purpose: user-authorized BF16 sign-pipe DC workflow example.\n"
        "Source commit: {}\n\nSource fingerprint: {}\n\n"
        "One SystemVerilog template, copied byte-for-byte to {}; no Chisel elaboration.\n"
        "Config: {}; top: {}; parameters: none.\n\n"
        "Validate with: python3 scripts/dc_example.py verify --export-id {}\n".format(
            export_id, commit, fingerprint, rtl_name, CONFIG, config["top"], export_id), encoding="utf-8")
    print("GENERATED " + export_id, flush=True)
    return export_id


def verify_example(export_id):
    export = contained(ROOT / "hw/rtl", export_id)
    manifest = read_json(export / "manifest.json")
    require(manifest["status"] == "generated", "Verification requires a new generated export")
    for name, expected in manifest["source_inputs"].items():
        require(sha256(contained(ROOT, name)) == expected, "Source changed; export again: " + name)
    for item in manifest["files"]:
        require(sha256(contained(export, item["path"])) == item["sha256"], "Exported RTL changed")
    config = read_json(ROOT / manifest["config_path"])
    verification_id = "rtl-" + export_id
    run = ROOT / "hw/test/runs" / verification_id
    run.mkdir(parents=True, exist_ok=False)
    iverilog, vvp = shutil.which("iverilog"), shutil.which("vvp")
    require(iverilog and vvp, "Icarus iverilog/vvp are required")
    version = command_output([iverilog, "-V"]).splitlines()[0]
    vvp_version = command_output([vvp, "-V"]).splitlines()[0]
    vectors = run / "vectors.txt"
    reference_command = [sys.executable, str(ROOT / config["reference"]), "--output", str(vectors),
                         "--seed", str(config["seed"]), "--random-cycles", str(config["random_cycles"])]
    require(logged(reference_command, ROOT, run / "reference.log") == 0, "Reference vector generation failed")
    metadata = read_json(Path(str(vectors) + ".json"))
    executable = run / "simulation.vvp"
    compile_command = [iverilog, "-g2012", "-s", "Bf16SignPipeTb", "-o", str(executable),
                       "-f", str(export / "files.f"), str(ROOT / config["testbench"])]
    sim_command = [vvp, str(executable), "+vectors=" + str(vectors)]
    input_paths = [ROOT / n for n in manifest["source_inputs"]]
    input_paths += [vectors, Path(str(vectors) + ".json"), export / "files.f"]
    input_paths += [export / item["path"] for item in manifest["files"]]
    before = {str(p): sha256(p) for p in input_paths}
    compile_rc = logged(compile_command, export, run / "compile.log")
    simulation_rc = logged(sim_command, run, run / "simulation.log") if compile_rc == 0 else None
    text = (run / "simulation.log").read_text() if (run / "simulation.log").is_file() else ""
    matches = re.findall(r"BF16_SIGN_PIPE_PASS cycles=(\d+) valid=(\d+) bubbles=(\d+) resets=(\d+)", text)
    expected = [metadata["counts"][key] for key in ("cycles", "valid", "bubbles", "resets")]
    inputs_unchanged = all(p.is_file() and sha256(p) == before[str(p)] for p in input_paths)
    passed = (compile_rc == 0 and simulation_rc == 0 and len(matches) == 1 and
              [int(v) for v in matches[0]] == expected and inputs_unchanged)
    roles = [(ROOT / config["testbench"], "testbench"), (ROOT / config["reference"], "reference"),
             (ROOT / CONFIG, "config"), (ROOT / config["spec"], "spec"),
             (ROOT / "scripts/dc_example.py", "verification_driver"),
             (ROOT / "scripts/rtl_gate.py", "gate"), (vectors, "vectors"),
             (Path(str(vectors) + ".json"), "vector_metadata"), (run / "compile.log", "compiler_log")]
    if (run / "simulation.log").is_file():
        roles.append((run / "simulation.log", "log"))
    receipt = {"schema_version": 1, "verification_id": verification_id, "export_id": export_id,
               "status": "passed" if passed else "failed", "method": "systemverilog_testbench",
               "numerical_pass": passed, "protocol_pass": passed,
               "numeric_semantics": config["spec"] + ": bit-exact sign XOR, no arithmetic rounding",
               "coverage_matrix": metadata, "seeds": [config["seed"]],
               "simulator": {"name": "Icarus Verilog", "version": version, "runtime_version": vvp_version,
                             "compiler_sha256": sha256(iverilog), "runtime_sha256": sha256(vvp)},
               "command": [{"argv": reference_command, "cwd": str(ROOT)},
                           {"argv": compile_command, "cwd": str(export)}, {"argv": sim_command, "cwd": str(run)}],
               "exit_codes": {"compile": compile_rc, "simulation": simulation_rc},
               "inputs_unchanged": inputs_unchanged, "finished_utc": utc(),
               "rtl_sha256": {f["path"]: f["sha256"] for f in manifest["files"]},
               "files_f_sha256": sha256(export / "files.f"),
               "inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p), "role": role}
                          for p, role in roles]}
    dump(run / "verification.json", receipt)
    manifest["status"] = receipt["status"]
    manifest["verification"] = {"path": (run / "verification.json").relative_to(ROOT).as_posix(),
                                "sha256": sha256(run / "verification.json")}
    dump(export / "manifest.json", manifest)
    with (export / "README.md").open("a", encoding="utf-8") as output:
        output.write("\nRTL verification status: {}. Tool: {}.\nCounts: {}\nEvidence: {}\n".format(
            receipt["status"], version, metadata["counts"], manifest["verification"]["path"]))
    if executable.is_file():
        executable.unlink()
    require(passed, "RTL verification failed; inspect " + str(run))
    verify_export(export_id, ROOT)
    print("RTL PASSED " + json.dumps(metadata["counts"]), flush=True)
    return run


def run_example(args):
    export_id = export_example()
    verification_run = verify_example(export_id)
    run_id = args.run_id or "dc-" + export_id
    runner = [sys.executable, str(ROOT / "hw/dc_syn/scripts/run_dc.py")]
    selection = ["--export-id", export_id, "--technology", str(args.technology.resolve()),
                 "--constraints", str(args.constraints.resolve()), "--machine", str(args.machine.resolve())]
    flow = {"schema_version": 1, "export_id": export_id, "run_id": run_id, "rtl_status": "passed",
            "dc_status": "not_run", "area_um2": None, "setup": None, "hold": None, "commands": []}
    for stage, command in (("check", runner + ["check"] + selection),
                           ("prepare", runner + ["prepare"] + selection + ["--run-id", run_id]),
                           ("run", runner + ["run", "--run-id", run_id])):
        rc = logged(command, ROOT, verification_run / ("dc_" + stage + ".log"))
        flow["commands"].append({"stage": stage, "argv": command, "exit_code": rc})
        summary = ROOT / "hw/dc_syn/runs" / run_id / "summary.json"
        if stage == "run" and summary.is_file():
            result = read_json(summary)
            require(result["export_id"] == export_id and result["run_id"] == run_id,
                    "DC summary belongs to a different export/run")
            flow.update(dc_status=result["status"], timing_status=result["timing_status"],
                        area_um2=result["area"]["total_cell_area_um2"], setup=result["setup"], hold=result["hold"],
                        summary=summary.relative_to(ROOT).as_posix())
        if rc:
            if stage != "run":
                flow["dc_status"] = "blocked_" + stage
            dump(verification_run / "flow.json", flow)
            print("DC {} returned {}; log: {}".format(stage, rc, verification_run / ("dc_" + stage + ".log")), flush=True)
            print(json.dumps(flow, indent=2), flush=True)
            return rc
    dump(verification_run / "flow.json", flow)
    print(json.dumps(flow, indent=2), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("export", help="Create a generated export; never marks it passed")
    verify = commands.add_parser("verify", help="Run a real SV testbench and issue bound evidence")
    verify.add_argument("--export-id", required=True)
    run = commands.add_parser("run", help="Export, RTL-verify, check, prepare and run real DC")
    for key in ("technology", "constraints", "machine"):
        run.add_argument("--" + key, required=True, type=Path)
    run.add_argument("--run-id")
    args = parser.parse_args()
    try:
        if args.command == "export":
            export_example()
        elif args.command == "verify":
            verify_example(args.export_id)
        elif args.command == "run":
            return run_example(args)
        else:
            parser.print_help()
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("DC example rejected: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
