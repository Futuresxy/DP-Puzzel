"""Software-only fixtures: never launch DC, a simulator, or an EDA setup script."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hw/dc_syn/scripts"))
from rtl_gate import sha256, verify_export
from report_dc import timing
from run_dc import tcl_string
import dc_example

EXPORT = "Fixture__test__20261024T010203000000Z__0123456789ab"

# This process fabricates parser fixtures ONLY inside TemporaryDirectory. It is
# not a synthesis implementation, numerical model, or project measurement.
FAKE_TOOL = '''#!/usr/bin/env python3
from pathlib import Path
import os
r=Path('.')
if os.environ.get('DC_FIXTURE_MODE') == 'empty':
    raise SystemExit(0)
for name in ['reports','netlist','work/WORK','work/alib']:
    (r/name).mkdir(parents=True,exist_ok=True)
(r/'work/WORK/temp').write_text('disposable test bytes')
for name in ['units.rpt','check_design.rpt','area_hierarchy.rpt','constraints.rpt','reference.rpt','cell_usage.tsv']:
    (r/'reports'/name).write_text('TEST FIXTURE ONLY')
(r/'reports/area.rpt').write_text('  testlib (File: /fixture/testlib.db)\\nTotal cell area: 10\\nCombinational area: 6\\nNoncombinational area: 4\\n')
(r/'reports/quality.tsv').write_text('design_check_pass\\t1\\nunresolved_leaf_count\\t0\\nclock_count\\t1\\n')
(r/'reports/check_timing.rpt').write_text('DP_TIMING_CHECKS_BEGIN\\nDP_TIMING_CHECKS_END\\n')
(r/'reports/qor.rpt').write_text('Version: FIXTURE\\nDesign  WNS: 0 TNS: 0 Number of Violating Paths: 0\\nDesign (Hold)  WNS: 0 TNS: 0 Number of Violating Paths: 0\\n')
for name in ['timing_setup.rpt','timing_hold.rpt']:
    (r/'reports'/name).write_text('Startpoint: fixture\\nEndpoint: fixture\\nslack (MET) 0.000001\\n')
for name in ['Fixture_mapped.v','Fixture.sdc','Fixture.ddc']:
    (r/'netlist'/name).write_text('TEST FIXTURE ONLY')
(r/'DC_COMPLETE').write_text('DP_DC_V1_EXPORTS_COMPLETE\\n')
mode=os.environ.get('DC_FIXTURE_MODE')
if mode == 'hold_fail':
    (r/'reports/timing_hold.rpt').write_text('slack (VIOLATED) -0.000001\\n')
elif mode == 'unknown':
    (r/'reports/timing_hold.rpt').unlink()
elif mode == 'unconstrained':
    with (r/'reports/check_timing.rpt').open('a') as stream:
        stream.write('WARNING: The following endpoints are not constrained for maximum delay.\\n')
elif mode == 'wrong_library':
    p=r/'reports/area.rpt'
    p.write_text(p.read_text().replace('testlib (File:', 'wronglib (File:'))
elif mode == 'license_error':
    print('Fatal: Design Compiler is not enabled. (DCSH-1)')
elif mode == 'ignored_constraint':
    print('Warning: constraint ignored by tool')
elif mode == 'drift':
    import json
    config=json.loads((r/'inputs/resolved.json').read_text())
    Path(config['gate']['sources'][0]).write_text('changed during fake process')
'''


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dc flow [fixture] ")
        self.root = Path(self.temp.name)
        self.dc = self.root / "hw/dc_syn"
        for name in ("scripts/rtl_gate.py", "hw/dc_syn/scripts/run_dc.py", "hw/dc_syn/scripts/report_dc.py",
                     "hw/dc_syn/templates/DC.tcl", "hw/dc_syn/templates/report.md.in"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(ROOT / name), str(target))
        self.export = self.root / "hw/rtl" / EXPORT
        (self.export / "src").mkdir(parents=True)
        (self.export / "src/Fixture.sv").write_text("// Software gate fixture, never simulated\nmodule Fixture; endmodule\n")
        (self.export / "files.f").write_text("src/Fixture.sv\n")
        (self.export / "README.md").write_text("Software fixture; not verified project hardware\n")
        self.evidence_path = self.root / "hw/test/runs/fixture/verification.json"
        self.inputs = []
        for role, name in (("testbench", "hw/test/tb/fixture.sv"), ("reference", "hw/test/reference/fixture.txt"),
                           ("vectors", "hw/test/vectors/fixture.txt"), ("log", "hw/test/runs/fixture/test.txt")):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("SOFTWARE FIXTURE ONLY " + role)
            self.inputs.append({"path": name, "sha256": sha256(p), "role": role})
        payload = {"src/Fixture.sv": sha256(self.export / "src/Fixture.sv")}
        self.evidence = {"schema_version": 1, "status": "passed", "export_id": EXPORT,
                         "verification_id": "SOFTWARE-FIXTURE-NOT-A-REAL-PASS", "method": "systemverilog_testbench",
                         "rtl_sha256": payload, "files_f_sha256": sha256(self.export / "files.f"),
                         "numerical_pass": True, "protocol_pass": True, "command": ["fixture"],
                         "numeric_semantics": "fixture", "coverage_matrix": ["fixture"], "seeds": [1],
                         "simulator": {"version": "fixture"}, "inputs": self.inputs}
        self.manifest = {"schema_version": 1, "export_id": EXPORT, "status": "passed", "top": "Fixture",
                         "module_map": {"Fixture": {"chisel_class": "fixture.Fixture", "source_file": "fixture.scala"}},
                         "files": [{"path": n, "sha256": h, "role": "source"} for n, h in payload.items()]}
        self.refresh_receipt()
        self.tool = self.root / "fake tool [no EDA]"
        self.tool.write_text(FAKE_TOOL.replace("#!/usr/bin/env python3", "#!" + sys.executable))
        self.tool.chmod(0o755)
        lib = self.root / "testlib.db"
        lib.write_text("not a real technology library")
        self.tech_path = self.root / "technology.json"
        dump(self.tech_path, {"schema_version": 1, "technology_id": "fixture", "process": "fixture",
                              "pvt": {"corner": "fixture"}, "target_libraries": ["testlib"],
                              "operating_library": "testlib", "operating_condition": "fixture",
                              "wire_load_model": "fixture", "area_unit": "um2", "multi_vt": None})
        self.constraints = self.root / "constraints.json"
        shutil.copyfile(str(ROOT / "hw/dc_syn/constraints/reference-1410mhz.json"), str(self.constraints))
        self.machine = self.root / "machine.local.json"
        dump(self.machine, {"schema_version": 1, "dc_shell": str(self.tool), "setup_script": "",
                            "libraries": {"testlib": str(lib)}})

    def tearDown(self):
        self.temp.cleanup()

    def refresh_receipt(self):
        dump(self.evidence_path, self.evidence)
        self.manifest["verification"] = {"path": "hw/test/runs/fixture/verification.json",
                                         "sha256": sha256(self.evidence_path)}
        dump(self.export / "manifest.json", self.manifest)

    def cli(self, *args, **kwargs):
        env = dict(os.environ)
        env.update(kwargs.get("env", {}))
        # External setup is never supplied by these tests.
        return subprocess.run([sys.executable, str(self.dc / "scripts/run_dc.py")] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    def selection(self):
        return ["--export-id", EXPORT, "--technology", str(self.tech_path),
                "--constraints", str(self.constraints), "--machine", str(self.machine)]

    def prepare(self):
        result = self.cli("prepare", *self.selection(), "--run-id", "fixture-run")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return self.dc / "runs/fixture-run"

    def completed(self):
        run = self.prepare()
        result = self.cli("run", "--run-id", run.name)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return run

    def test_check_and_prepare_never_launch_tool(self):
        result = self.cli("check", *self.selection())
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertFalse((self.dc / "runs").exists())
        run = self.prepare()
        self.assertFalse((run / "DC_COMPLETE").exists())
        self.assertFalse((run / "summary.json").exists())
        self.assertEqual(self.cli("prepare", *self.selection(), "--run-id", run.name).returncode, 2)

    def test_rtl_and_testbench_changes_rejected(self):
        verify_export(EXPORT, self.root)
        (self.export / "src/Fixture.sv").write_text("changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify_export(EXPORT, self.root)
        entry = self.manifest["files"][0]
        entry["sha256"] = sha256(self.export / entry["path"])
        self.evidence["rtl_sha256"][entry["path"]] = entry["sha256"]
        self.refresh_receipt()
        (self.root / self.inputs[0]["path"]).write_text("changed testbench")
        with self.assertRaisesRegex(ValueError, "Stale verification"):
            verify_export(EXPORT, self.root)

    def test_handwritten_sv_requires_real_byte_identical_source(self):
        source = self.root / "example.sv.in"
        source.write_bytes((self.export / "src/Fixture.sv").read_bytes())
        mapping = {"source_language": "systemverilog", "chisel_class": None,
                   "source_file": "example.sv.in", "source_sha256": sha256(source),
                   "rtl_file": "src/Fixture.sv"}
        self.manifest["module_map"] = {"Fixture": mapping}
        self.refresh_receipt()
        result = verify_export(EXPORT, self.root)
        self.assertIn(str(source), result["tracked"])
        source.write_text("different source bytes")
        with self.assertRaisesRegex(ValueError, "Stale SystemVerilog source"):
            verify_export(EXPORT, self.root)
        mapping["source_sha256"] = sha256(source)
        self.refresh_receipt()
        with self.assertRaisesRegex(ValueError, "byte-for-byte"):
            verify_export(EXPORT, self.root)

    def test_unknown_source_language_is_rejected(self):
        self.manifest["module_map"]["Fixture"]["source_language"] = "unknown"
        self.refresh_receipt()
        with self.assertRaisesRegex(ValueError, "module/source mapping"):
            verify_export(EXPORT, self.root)

    def test_example_failed_prepare_never_reuses_an_old_area(self):
        evidence_dir = self.root / "hw/test/runs/example"
        evidence_dir.mkdir(parents=True)
        dump(self.dc / "runs/old-run/summary.json", {"status": "measured", "timing_status": "PASS",
             "export_id": "different-export", "run_id": "old-run", "area": {"total_cell_area_um2": 999},
             "setup": {"status": "PASS"}, "hold": {"status": "PASS"}})
        args = SimpleNamespace(run_id="old-run", technology=self.tech_path,
                               constraints=self.constraints, machine=self.machine)
        with patch.object(dc_example, "ROOT", self.root), patch.object(dc_example, "export_example", return_value=EXPORT), \
             patch.object(dc_example, "verify_example", return_value=evidence_dir), \
             patch.object(dc_example, "logged", side_effect=[0, 2]), patch("builtins.print"):
            self.assertEqual(dc_example.run_example(args), 2)
        flow = json.loads((evidence_dir / "flow.json").read_text())
        self.assertEqual(flow["dc_status"], "blocked_prepare")
        self.assertIsNone(flow["area_um2"])

    def test_missing_protocol_evidence_and_generated_status_rejected(self):
        self.evidence["protocol_pass"] = False
        self.refresh_receipt()
        self.assertEqual(self.cli("check", *self.selection()).returncode, 2)
        self.evidence["protocol_pass"] = True
        self.manifest["status"] = "generated"
        self.refresh_receipt()
        self.assertEqual(self.cli("check", *self.selection()).returncode, 2)

    def test_extra_source_and_external_include_rejected(self):
        extra = self.export / "src/unlisted.svh"
        extra.write_text("untracked")
        with self.assertRaisesRegex(ValueError, "Unlisted"):
            verify_export(EXPORT, self.root)
        extra.unlink()
        source = self.export / "src/Fixture.sv"
        source.write_text('`include "/outside/fixture.svh"\nmodule Fixture; endmodule\n')
        self.manifest["files"][0]["sha256"] = sha256(source)
        self.evidence["rtl_sha256"]["src/Fixture.sv"] = sha256(source)
        self.refresh_receipt()
        with self.assertRaisesRegex(ValueError, "External include"):
            verify_export(EXPORT, self.root)

    def test_changed_prepared_constraints_block_launch(self):
        run = self.prepare()
        self.constraints.write_text("changed after preparation")
        self.assertEqual(self.cli("run", "--run-id", run.name).returncode, 2)
        self.assertFalse((run / "logs").exists())

    def test_zero_process_exit_without_completion_is_invalid(self):
        run = self.prepare()
        result = self.cli("run", "--run-id", run.name, env={"DC_FIXTURE_MODE": "empty"})
        self.assertEqual(result.returncode, 2)
        summary = json.loads((run / "summary.json").read_text())
        self.assertFalse(summary["timing_pass"])
        self.assertIsNone(summary["area"]["total_cell_area_um2"])

    def test_failure_unknown_and_library_checks_are_distinct(self):
        self.prepare()
        for mode, code in (("hold_fail", 3), ("unknown", 4), ("unconstrained", 2),
                           ("wrong_library", 2), ("license_error", 2), ("ignored_constraint", 2), ("drift", 2)):
            with self.subTest(mode=mode):
                run_id = "fixture-" + mode
                prepared = self.cli("prepare", *self.selection(), "--run-id", run_id)
                self.assertEqual(prepared.returncode, 0, prepared.stderr.decode())
                result = self.cli("run", "--run-id", run_id, env={"DC_FIXTURE_MODE": mode})
                self.assertEqual(result.returncode, code, result.stdout.decode() + result.stderr.decode())
                summary = json.loads((self.dc / "runs" / run_id / "summary.json").read_text())
                self.assertFalse(summary["timing_pass"])
                self.assertFalse(summary["power_ready"])
                self.assertEqual(summary["netlist_equivalence"], "not_run")
                if mode in ("hold_fail", "unknown"):
                    self.assertTrue(summary["synthesis_valid"])
                    self.assertEqual(summary["area"]["total_cell_area_um2"], 10)

    def test_output_integrity_and_safe_cleanup(self):
        run = self.completed()
        self.assertEqual(self.cli("report", "--run-id", run.name).returncode, 0)
        self.assertEqual(self.cli("run", "--run-id", run.name).returncode, 2)
        mapped = run / "netlist/Fixture_mapped.v"
        before = sha256(mapped)
        self.assertEqual(self.cli("clean", "--run-id", run.name).returncode, 0)
        self.assertTrue((run / "work").exists())
        self.assertEqual(self.cli("clean", "--run-id", run.name, "--apply").returncode, 0)
        self.assertFalse((run / "work").exists())
        self.assertEqual(sha256(mapped), before)
        self.assertEqual(self.cli("report", "--run-id", run.name).returncode, 0)
        mapped.write_text("tampered")
        self.assertEqual(self.cli("report", "--run-id", run.name).returncode, 2)

    def test_active_and_symlink_cleanup_rejected(self):
        run = self.completed()
        (run / ".running").mkdir()
        self.assertEqual(self.cli("clean", "--run-id", run.name, "--apply").returncode, 2)
        (run / ".running").rmdir()
        (run / "work/escape").symlink_to(self.root)
        self.assertEqual(self.cli("clean", "--run-id", run.name, "--apply").returncode, 2)
        self.assertEqual(self.cli("clean", "--run-id", "../escape", "--apply").returncode, 2)

    def test_hold_violation_hidden_by_rounded_qor_is_failure(self):
        qor = "Design (Hold) WNS: 0.00 TNS: 0.00 Number of Violating Paths: 0"
        result = timing(qor, "slack (VIOLATED) -0.000001", True)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(timing(qor, "", True)["status"], "UNKNOWN")

    def test_all_path_groups_are_accounted_for(self):
        qor = "Timing Path Group 'first'\nCritical Path Slack: 1\nDesign WNS: -1 TNS: -2 Number of Violating Paths: 3"
        result = timing(qor, "slack (MET) 1")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["violating_paths"], 3)

    def test_missing_library_and_malformed_constraints_rejected(self):
        data = json.loads(self.machine.read_text())
        Path(data["libraries"]["testlib"]).unlink()
        self.assertEqual(self.cli("check", *self.selection()).returncode, 2)
        constraints = json.loads(self.constraints.read_text())
        constraints["period_ns"] = 0
        dump(self.constraints, constraints)
        self.assertEqual(self.cli("prepare", *self.selection()).returncode, 2)

    @unittest.skipUnless(shutil.which("tclsh"), "Tcl not installed")
    def test_tcl_quoting_and_template_syntax(self):
        path = self.root / "quoting.tcl"
        value = 'path $var [no execution] \\" braces {} 中文'
        path.write_text('set value ' + tcl_string(value) + '\nputs $value\n', encoding="utf-8")
        result = subprocess.run(["tclsh", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout.decode().strip(), value)
        path.write_text('set f [open [lindex $argv 0]]\nset s [read $f]\nclose $f\nif {![info complete $s]} {exit 2}\n')
        self.assertEqual(subprocess.call(["tclsh", str(path), str(ROOT / "hw/dc_syn/templates/DC.tcl")]), 0)


if __name__ == "__main__":
    unittest.main()
