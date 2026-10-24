#!/usr/bin/env python3
"""Export and RTL-verify the BF16 test fixture. This test driver never invokes DC."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from rtl_gate import contained, read_json, require, rtl_fingerprint, verify_export

CONFIG = "hw/configs/bf16_sign_pipe_example.json"
TEST_CONFIG = "hw/test/configs/bf16_sign_pipe.json"


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
    config.update(read_json(ROOT / TEST_CONFIG))
    require(config["top"] == "Bf16SignPipe" and config["schema_version"] == 1, "Unsupported example config")
    names = [CONFIG, TEST_CONFIG, config["source_template"], config["spec"], config["testbench"], config["reference"],
             "hw/test/scripts/bf16_sign_pipe.py", "scripts/rtl_gate.py"]
    timestamp = utc()
    export_id = "{}__{}__{}__000000000000".format(config["top"], config["config_id"], timestamp)
    export = ROOT / "hw/rtl" / export_id
    (export / "src").mkdir(parents=True, exist_ok=False)
    rtl_name = "src/" + config["top"] + ".sv"
    shutil.copyfile(str(ROOT / config["source_template"]), str(export / rtl_name))
    (export / "files.f").write_text(rtl_name + "\n", encoding="utf-8")
    fingerprint = rtl_fingerprint(export)
    export_id = "{}__{}__{}__{}".format(config["top"], config["config_id"], timestamp, fingerprint[:12])
    destination = ROOT / "hw/rtl" / export_id
    export.rename(destination)
    export = destination
    commit = command_output(["git", "rev-parse", "HEAD"]).strip()
    manifest = {"schema_version": 2, "export_id": export_id, "top": config["top"], "status": "generated",
                "created_utc": utc(), "config_path": CONFIG, "parameters": config["parameters"],
                "source_commit": commit, "rtl_fingerprint": fingerprint, "source_inputs": names,
                "exporter": {"command": [sys.executable, "hw/test/scripts/bf16_sign_pipe.py", "export"],
                             "python": sys.version.split()[0], "kind": "byte_identical_systemverilog"},
                "module_map": {config["top"]: {"source_language": "systemverilog", "chisel_class": None,
                    "source_file": config["source_template"],
                    "rtl_file": rtl_name}},
                "files": [{"path": rtl_name, "role": "source"}]}
    dump(export / "manifest.json", manifest)
    (export / "README.md").write_text(
        "# {}\n\nStatus: generated (RTL simulation not yet run).\n\n"
        "Purpose: user-authorized BF16 sign-pipe DC workflow example.\n"
        "Source commit: {}\n\nRTL directory fingerprint: {}\n\n"
        "One SystemVerilog template, copied byte-for-byte to {}; no Chisel elaboration.\n"
        "Config: {}; top: {}; parameters: none.\n\n"
        "Validate with: python3 hw/test/scripts/bf16_sign_pipe.py verify --export-id {}\n".format(
            export_id, commit, fingerprint, rtl_name, CONFIG, config["top"], export_id), encoding="utf-8")
    print("GENERATED " + export_id, flush=True)
    return export_id


def verify_example(export_id):
    export = contained(ROOT / "hw/rtl", export_id)
    manifest = read_json(export / "manifest.json")
    require(manifest["status"] == "generated", "Verification requires a new generated export")
    require(rtl_fingerprint(export) == manifest["rtl_fingerprint"], "Exported RTL directory changed")
    config = read_json(ROOT / manifest["config_path"])
    config.update(read_json(ROOT / TEST_CONFIG))
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
    input_paths = [ROOT / config["testbench"], ROOT / config["reference"], vectors]
    before = {str(p): p.stat().st_mtime for p in input_paths}
    compile_rc = logged(compile_command, export, run / "compile.log")
    simulation_rc = logged(sim_command, run, run / "simulation.log") if compile_rc == 0 else None
    text = (run / "simulation.log").read_text() if (run / "simulation.log").is_file() else ""
    matches = re.findall(r"BF16_SIGN_PIPE_PASS cycles=(\d+) valid=(\d+) bubbles=(\d+) resets=(\d+)", text)
    expected = [metadata["counts"][key] for key in ("cycles", "valid", "bubbles", "resets")]
    inputs_unchanged = (rtl_fingerprint(export) == manifest["rtl_fingerprint"] and
                        all(p.is_file() and p.stat().st_mtime == before[str(p)] for p in input_paths))
    passed = (compile_rc == 0 and simulation_rc == 0 and len(matches) == 1 and
              [int(v) for v in matches[0]] == expected and inputs_unchanged)
    roles = [(ROOT / config["testbench"], "testbench"), (ROOT / config["reference"], "reference"),
             (ROOT / CONFIG, "config"), (ROOT / TEST_CONFIG, "test_config"), (ROOT / config["spec"], "spec"),
             (ROOT / "hw/test/scripts/bf16_sign_pipe.py", "verification_driver"),
             (ROOT / "scripts/rtl_gate.py", "gate"), (vectors, "vectors"),
             (Path(str(vectors) + ".json"), "vector_metadata"), (run / "compile.log", "compiler_log")]
    if (run / "simulation.log").is_file():
        roles.append((run / "simulation.log", "log"))
    receipt = {"schema_version": 2, "verification_id": verification_id, "export_id": export_id,
               "status": "passed" if passed else "failed", "method": "systemverilog_testbench",
               "numerical_pass": passed, "protocol_pass": passed,
               "numeric_semantics": config["spec"] + ": bit-exact sign XOR, no arithmetic rounding",
               "coverage_matrix": metadata, "seeds": [config["seed"]],
               "simulator": {"name": "Icarus Verilog", "version": version, "runtime_version": vvp_version},
               "command": [{"argv": reference_command, "cwd": str(ROOT)},
                           {"argv": compile_command, "cwd": str(export)}, {"argv": sim_command, "cwd": str(run)}],
               "exit_codes": {"compile": compile_rc, "simulation": simulation_rc},
               "inputs_unchanged": inputs_unchanged, "finished_utc": utc(),
               "rtl_fingerprint": manifest["rtl_fingerprint"],
               "inputs": [{"path": p.relative_to(ROOT).as_posix(), "role": role}
                          for p, role in roles]}
    dump(run / "verification.json", receipt)
    manifest["status"] = receipt["status"]
    manifest["verification"] = {"path": (run / "verification.json").relative_to(ROOT).as_posix()}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("export", help="Create a generated export; never marks it passed")
    verify = commands.add_parser("verify", help="Run a real SV testbench and issue bound evidence")
    verify.add_argument("--export-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "export":
            export_example()
        elif args.command == "verify":
            verify_example(args.export_id)
        else:
            parser.print_help()
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("BF16 test rejected: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
