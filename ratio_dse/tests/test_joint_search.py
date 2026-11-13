import random
import csv
import json
import tempfile
import unittest
from math import ceil
from pathlib import Path

from ratio_dse.area_model import import_profiles
from ratio_dse.common import PACKAGE, read_json
from ratio_dse.dse.joint_search import construct_deployments, run, select_designs
from ratio_dse.dse.model import buffered_lane_service, operator_cost, tile_groups
from ratio_dse.formats import layout


def explicit_wave(steps, contexts, ii, latency, feedback, read_cycles, write_cycles, banks):
    """Independent event oracle: bank refill, per-context RAW and final drain."""
    bank_free = [0] * banks
    feedback_ready = [0] * contexts
    read_end = next_issue = last_result = 0
    for step in range(steps):
        bank = step % banks
        read_end = max(read_end, bank_free[bank]) + read_cycles
        for context in range(contexts):
            issue_at = max(read_end, next_issue, feedback_ready[context])
            next_issue = issue_at + ii
            feedback_ready[context] = issue_at + feedback
            last_result = max(last_result, issue_at + latency, next_issue)
        bank_free[bank] = next_issue
    return last_result + write_cycles


class BufferedScheduleTests(unittest.TestCase):
    def test_round_formula_matches_bank_and_raw_event_oracle(self):
        rng = random.Random(20261113)
        for _ in range(500):
            steps, contexts = rng.randint(1, 40), rng.randint(1, 12)
            ii, latency = rng.randint(1, 4), rng.randint(1, 16)
            feedback = rng.randint(latency, latency + 8)
            read_bw, write_bw = rng.randint(1, 100), rng.randint(1, 100)
            ab, d = rng.randint(1, 200), rng.randint(1, 80)
            refill, store = ceil(contexts * ab / read_bw), ceil(contexts * d / write_bw)
            for banks in (1, 2):
                cost = buffered_lane_service(((steps, contexts),), ii, latency, feedback,
                                             contexts, ab, d, read_bw, write_bw, banks)
                expected = explicit_wave(steps, contexts, ii, latency, feedback, refill, store, banks)
                self.assertEqual(cost[0], expected)
                self.assertLessEqual(cost[0], sum(cost[1:4]))

    def test_first_fill_and_last_drain_are_not_hidden(self):
        # Three rounds: bank fills 0..10, 10..20, 20..30;
        # issues at 10,20,30; final result 38 and write 38..39.
        pingpong = buffered_lane_service(((3, 1),), 1, 8, 8, 1, 100, 10, 10, 10, 2)
        self.assertEqual(pingpong[:4], (39, 24, 30, 1))
        single = buffered_lane_service(((3, 1),), 1, 8, 8, 1, 100, 10, 10, 10, 1)
        self.assertEqual(single[0], 41)
        first = buffered_lane_service(((1, 1),), 1, 8, 8, 1, 100, 10, 10, 10, 2)
        self.assertEqual(first[0], 19)

    def test_partial_waves_and_k_groups_drain_separately(self):
        expected = 0
        for steps, active in ((1, 3), (7, 5), (7, 5), (7, 5), (7, 4)):
            expected += explicit_wave(steps, active, 1, 8, 8, ceil(active * 32 / 17),
                                      ceil(active * 64 / 11), 2)
        actual = buffered_lane_service(((1, 3), (7, 19)), 1, 8, 8, 5, 32, 64, 17, 11, 2)
        self.assertEqual(actual[0], expected)

    def test_core_cap_and_same_capacity_buffer_tradeoff(self):
        mode = {"power_dynamic_w": 0.02, "power_leakage_w": 0.001, "native_k": 16,
                "ii_cycles": 1, "latency_cycles": 8, "macs_per_cycle": 16, "input_layout": layout("bf16")}
        broadcast = {"group_shape": [4, 4], "share_a_across_column_groups": False,
                     "share_b_across_row_groups": False}
        deployment = {"m_array": 4, "n_array": 4, "core_count": 4, "arrays_per_core": 2,
                      "dp_per_core": 32, "frequency_hz": 1_000_000_000, "broadcast_model": broadcast}
        shape = {"kind": "dense", "m": 16, "n": 16, "k": 48}
        geometry, groups = tile_groups(shape, 4, 4, 16, "pooled_output_tiles")
        settings = {"idle_fraction": 0, "cap_w": 1.1, "include_local": True, "local_tb_s": 1,
                    "write_read_ratio": 1, "contexts": 8, "buffer_bytes_per_array": 1024,
                    "io_schedule": "pingpong", "operand_delivery": "native_issue_width"}
        op = {"useful_macs": 16 * 16 * 48}
        core = operator_cost(op, geometry, groups, deployment, mode, settings | {"power_granularity": "core"})
        array = operator_cost(op, geometry, groups, deployment, mode, settings | {"power_granularity": "array"})
        self.assertEqual((core["eligible_cores"], core["eligible_arrays"], array["eligible_arrays"]), (1, 2, 3))
        self.assertEqual(core["effective_contexts"], 1)  # 2*256 + 64 bytes per context
        single = operator_cost(op, geometry, groups, deployment, mode,
                               settings | {"power_granularity": "core", "io_schedule": "single_buffer"})
        self.assertEqual(single["effective_contexts"], 3)
        self.assertLessEqual(core["buffer_required_bytes"], 1024)
        self.assertLessEqual(core["dp_envelope_w"], 1.1)
        self.assertIsNone(operator_cost(op, geometry, groups, deployment, mode,
                                       settings | {"buffer_bytes_per_array": 575}))


class JointConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hardware, _ = import_profiles(read_json(PACKAGE / "configs/area/dp_n12_20261112.lock.json"))
        cls.baseline = read_json(PACKAGE / "configs/area/sm_4x16x4.json")

    def test_same_area_more_baseline_dps_and_discrete_bandwidth_fill(self):
        shapes = [[16, 4], [16, 8], [8, 16], [16, 16]]
        rows = construct_deployments(self.hardware, self.baseline, shapes, 16)
        self.assertEqual(len({row["area_budget_um2"] for row in rows}), 1)
        base = [row for row in rows if row["profile_id"] == "H16Q32E64"]
        fixed = next(row for row in base if row["constraint_kind"] == "equal_array")
        filled = [row for row in base if row["bandwidth_filled"]]
        self.assertEqual({(row["m_array"], row["n_array"]) for row in filled}, {(16, 8), (8, 16)})
        for row in filled:
            self.assertGreater(row["dp_per_core"] * row["core_count"], fixed["dp_per_core"] * fixed["core_count"])
            self.assertLessEqual(row["area_pool_um2"], fixed["area_budget_um2"])
        too_large = next(row for row in base if row["m_array"] == row["n_array"] == 16)
        self.assertFalse(too_large["valid"])
        self.assertFalse(too_large["bandwidth_filled"])

    def test_empty_selection_is_explicit(self):
        self.assertEqual(select_designs([])[0]["status"], "no_feasible_candidate")

    def test_end_to_end_outputs_and_bidirectional_winners(self):
        config = read_json(PACKAGE / "configs/dse/joint_search.json") | {
            "workloads": ["ratio_dse/configs/compute/v41_prefill.json"], "anchor_length": 256,
            "legal_shapes": [[16, 4]], "local_read_tb_s_per_core": [16],
            "power_caps_w": [None], "io_schedules": ["pingpong"],
        }
        with tempfile.TemporaryDirectory() as temp:
            path, output = Path(temp) / "config.json", Path(temp) / "run"
            path.write_text(json.dumps(config))
            checks = run(path, output, ["integration-test"])
            self.assertGreater(checks["candidate_evaluations"], 0)
            self.assertTrue((output / "manifest.json").is_file())
            def rows(name):
                with (output / name).open() as stream:
                    return list(csv.DictReader(stream))
            candidates = rows("candidate_evaluations.csv")
            for selection in rows("workload_to_hardware.csv"):
                eligible = [row for row in candidates if row["plan"] == selection["plan"] and (
                    row["construction"] == "equal_array" if selection["construction_view"] == "equal_array"
                    else row["construction"] == "equal_input_bandwidth")]
                self.assertAlmostEqual(float(selection["winner_time_s"]), min(float(row["seconds"]) for row in eligible))
            for selection in rows("hardware_to_migration.csv"):
                eligible = [row for row in candidates if row["deployment_id"] == selection["deployment_id"]]
                self.assertAlmostEqual(float(selection["winner_time_s"]), min(float(row["seconds"]) for row in eligible))
            self.assertEqual({row["quality_status"] for row in candidates}, {"out_of_scope"})
            self.assertTrue(rows("winning_operator_breakdown.csv"))


if __name__ == "__main__":
    unittest.main()
