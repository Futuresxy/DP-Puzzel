import unittest
from collections import Counter

from ratio_dse.common import PACKAGE, read_json
from ratio_dse.compute_model import build_workload
from ratio_dse.dse.migration_selection import _plans, _select, _step_moves
from ratio_dse.dse.model import array_limit, group_service, pareto_indices, partition_tiles, power_terms, tile_groups


class DSEModelTests(unittest.TestCase):
    def test_partition_preserves_k_chains(self):
        histogram = ((1, 2), (3, 5))
        lanes = partition_tiles(histogram, 4)
        self.assertEqual(sum(lanes, Counter()), dict(histogram))
        self.assertEqual(sum(sum(k * n for k, n in lane.items()) for lane in lanes), 17)
        self.assertEqual(max(sum(lane.values()) for lane in lanes), 2)

    def test_multicore_schedule_with_private_port_shares(self):
        tiles = ((3, 2),)
        # On two cores, each array issues at cycles 0, 8, 16 and completes at 24.
        # Three 32-byte reads and one 16-byte write at 16 B/cycle cost 7 cycles.
        independent, active, _ = group_service(tiles, 2, 2, 1, 8, 8, 8, 32, 16, 16, 16)
        self.assertEqual((independent[:4], active), ((31, 24, 6, 1), 2))
        shared, _, _ = group_service(tiles, 2, 1, 1, 8, 8, 8, 32, 16, 16, 16)
        self.assertEqual(shared[:4], (38, 24, 12, 2))
        serial, _, _ = group_service(tiles, 1, 1, 1, 8, 8, 8, 32, 16, 16, 16)
        self.assertEqual(serial[:4], (39, 25, 12, 2))

    def test_power_cap_preserves_installed_leakage(self):
        mode = {"power_dynamic_w": 0.02, "power_leakage_w": 0.001}
        idle, increment = power_terms(64, 16, mode, 0)
        self.assertAlmostEqual(idle, 0.064)
        self.assertAlmostEqual(increment, 0.32)
        self.assertEqual(array_limit(4, 0.7, idle, increment), 1)
        self.assertEqual(array_limit(4, 0.05, idle, increment), 0)
        self.assertEqual(array_limit(4, None, idle, increment), 4)

    def test_expert_pooling_preserves_issued_work(self):
        shape = {"kind": "experts", "tokens_per_expert": [4, 2, 2, 0], "n": 7, "k": 33}
        pooled, _ = tile_groups(shape, 4, 4, 16, "pooled_output_tiles")
        isolated, groups = tile_groups(shape, 4, 4, 16, "isolated_weights")
        self.assertEqual(pooled, isolated)
        self.assertEqual(pooled["issue_requests"],
                         sum(reps * sum(k * n for k, n in group) for reps, group in groups))

    def test_pareto_preserves_ties(self):
        rows = [{"a": a, "b": b} for a, b in [(1, 2), (2, 1), (1, 2), (2, 2), (3, 1)]]
        self.assertEqual(pareto_indices(rows, ("a", "b")), [0, 1, 2])

    def test_migration_selection_uses_only_feasible_candidates(self):
        metrics = {"status": "analytical_uncalibrated", "coverage": 0.9, "dp_envelope_w": 100}
        baseline = metrics | {"profile": "H16Q32E64", "ratio": "1:2:4", "candidate_id": "base",
                              "seconds": 0.105, "dp_energy_j": 2}
        fast = metrics | {"profile": "H16Q64E64", "ratio": "1:4:4", "candidate_id": "fast",
                          "seconds": 0.100, "dp_energy_j": 3}
        blocked = {"profile": "H16Q128E256", "status": "infeasible_cap_buffer_or_missing_power"}
        selected = _select([baseline, blocked, fast])
        self.assertEqual(selected["feasible_profiles"], 2)
        self.assertEqual(selected["winner_ratio"], "1:4:4")
        self.assertEqual(selected["energy_winner_ratio"], "1:2:4")
        self.assertAlmostEqual(selected["runner_up_gap_pct"], 5)
        self.assertEqual(_select([blocked])["status"], "no_feasible_profile")

    def test_staged_moves_separate_experts_projections_and_attention(self):
        for model, window_projection in (("v4", "window_kv"), ("v41", "swa_kv")):
            with self.subTest(model=model):
                options = read_json(PACKAGE / "configs" / "compute" / f"{model}_prefill.json")
                workload = build_workload(options | {"variant": "target_native_20261112"})
                plans = list(_plans(workload, "staged"))
                self.assertEqual([plan["name"] for plan in plans], ["baseline", "step1", "step2", "step3"])
                changed = [{(move["operator"], move["from_format"], move["to_format"])
                            for move in _step_moves(workload, before, after)}
                           for before, after in zip(plans, plans[1:])]
                fp8, fp4 = "mxfp8_e4m3", "mxfp4_e2m1"
                experts = {f"moe.{group}.{op}" for group in ("routed", "shared") for op in ("gate", "up", "down")}
                self.assertEqual(changed[0], {("o_group", "bf16", fp4)} | {(op, fp8, fp4) for op in experts})
                self.assertEqual(changed[1], {(op, fp8, fp4) for op in ("q_down", "q_up", "o_final", window_projection)})
                self.assertEqual(changed[2], {(op, "bf16", fp8) for op in ("swa.qk", "swa.pv", "csa.qk", "csa.pv")})
