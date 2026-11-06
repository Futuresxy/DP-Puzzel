import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_retention import FLOWS, PIN, pin_run, plan, remove_run


class RetentionTests(unittest.TestCase):
    def setUp(self):
        repo = tempfile.TemporaryDirectory()
        self.addCleanup(repo.cleanup)
        self.root = Path(repo.name)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        (self.root / ".gitignore").write_text("test/runs/\nhw/dc_syn/runs/\nhw/power/runs/\n")

    def make_run(self, flow, n, phase="finished"):
        timestamp = f"20261105T1000{n:02d}000000Z"
        run_id = f"dc_dp_top_110510{n:02d}" if flow == "dc" else timestamp
        path = self.root / FLOWS[flow] / run_id
        if flow == "rtl":
            name, data = "verilator-verilog-all-summary.json", [{"result": "PASS"}]
        elif flow == "cmodel":
            name, data = "summary.json", {"status": "passed"}
        else:
            name, data = "state.json", {"phase": phase, "finished_utc": timestamp}
        self.write(path / name, data)
        return path

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_each_flow_keeps_two_completed_runs(self):
        for flow in FLOWS:
            older = self.make_run(flow, 0)
            newer = [self.make_run(flow, i) for i in (1, 2)]
            decisions = dict(plan(self.root))
            self.assertEqual(decisions[older], "DELETE")
            self.assertTrue(older.is_dir())  # Planning is read-only.
            self.assertTrue(all(decisions[p] == "KEEP" for p in newer))
            remove_run(self.root, older)
            self.assertFalse(older.exists())

    def test_protected_runs_do_not_count_against_the_limit(self):
        receipt, scope, published, ordinary, recent, newest = [self.make_run("rtl", i) for i in range(6)]
        dc = self.make_run("dc", 0)
        repair = self.make_run("dc", 1)
        local_record = self.make_run("dc", 2)
        power = self.make_run("power", 10, "running")
        self.write(self.root / "hw/rtl/DP_example/manifest.json", {
            "verification": {"path": str(receipt / "verification.json")},
            "verified_scopes": [{"results_path": str(scope / "results.txt")}],
            "validation_runs": [{"results_path": str(ordinary / "results.txt")}],
        })
        self.write(repair / "inputs/resolved.json", {"hold_repair": {"source_run": dc.name}})
        self.write(power / "manifest.json", {"dc_run": repair.name})
        self.write(self.root / "hw/dc_syn/records/local.json", {"run": str(local_record)})
        self.write(self.root / "record.json", {"run": str(published)})
        subprocess.run(["git", "add", "record.json"], cwd=self.root, check=True)
        pinned = self.make_run("cmodel", 0)
        pin_run(self.root, pinned, "User confirmed release evidence")
        self.assertEqual(json.loads((pinned / PIN).read_text())["reason"], "User confirmed release evidence")
        decisions = dict(plan(self.root))
        for path in (receipt, scope, published, dc, repair, local_record):
            self.assertEqual(decisions[path], "REFERENCED_OR_TRACKED")
            with self.assertRaises(ValueError):
                remove_run(self.root, path)
        self.assertEqual(decisions[ordinary], "DELETE")
        self.assertEqual(decisions[recent], "KEEP")
        self.assertEqual(decisions[newest], "KEEP")
        self.assertEqual(decisions[pinned], "PINNED")
        self.assertEqual(decisions[power], "UNCLASSIFIED_OR_ACTIVE")
        with self.assertRaises(ValueError):
            remove_run(self.root, pinned)

    def test_active_unknown_tracked_and_symlink_are_not_removed(self):
        active = self.make_run("dc", 0)
        (active / ".running").mkdir()
        old = self.root / FLOWS["rtl"] / "manual"
        old.mkdir(parents=True)
        tracked = self.make_run("rtl", 0)
        subprocess.run(["git", "add", "-f", tracked], cwd=self.root, check=True)
        linked = self.make_run("rtl", 1)
        outside = self.root / "user-data"
        outside.write_text("keep")
        (linked / "outside").symlink_to(outside)
        decisions = dict(plan(self.root))
        self.assertEqual(decisions[active], "UNCLASSIFIED_OR_ACTIVE")
        self.assertEqual(decisions[old], "UNCLASSIFIED_OR_ACTIVE")
        self.assertEqual(decisions[tracked], "REFERENCED_OR_TRACKED")
        for path in (active, old, tracked, linked):
            with self.assertRaises(ValueError):
                remove_run(self.root, path)
        self.assertEqual(outside.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
