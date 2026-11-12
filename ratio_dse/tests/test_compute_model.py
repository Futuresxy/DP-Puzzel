import sys
import unittest
from collections import Counter
from unittest.mock import patch

from paper.scripts import deepseek_v41
from ratio_dse.area_model import enumerate_deployments, import_profiles
from ratio_dse.common import PACKAGE, read_json
from ratio_dse.compute_model import (build_workload, compare_plans, evaluate_workload, resolve_plan,
                                     validate_workload)
from ratio_dse.compute_model.precision import quality_status
from ratio_dse.compute_model.tiling import service_cycles, tile_geometry
from ratio_dse.compute_model.workload import MODEL_ROOT, _stats, candidate_runs, floor_runs, work_macs

CONFIG = PACKAGE / "configs/compute"


class TilingTests(unittest.TestCase):
    def test_dense_geometry_and_native_k_boundaries(self):
        shape = {"kind": "dense", "m": 17, "n": 5, "k": 33}
        self.assertEqual(work_macs(shape), 2805)
        self.assertEqual(tile_geometry(shape, 16, 4, 16)["issued_macs"], 12288)
        self.assertEqual(tile_geometry(shape, 16, 4, 32)["issued_macs"], 16384)
        for k, requests in [(15, 1), (16, 1), (17, 2), (47, 3)]:
            with self.subTest(k=k):
                self.assertEqual(tile_geometry(shape | {"m": 1, "n": 1, "k": k}, 16, 4, 16)["issue_requests"],
                                 requests)

    def test_ragged_qk_and_pv_and_indexed_positions(self):
        base = {"kind": "ragged", "m": 2, "fixed_dimension": 3,
                "layout": "compact_gather", "length_runs": [[1, 1, 1], [5, 5, 1]]}
        qk, pv = base | {"axis": "n"}, base | {"axis": "k"}
        self.assertEqual(work_macs(qk), 36)
        self.assertEqual(work_macs(pv), 36)
        self.assertEqual(tile_geometry(qk, 2, 2, 4)["issued_macs"], 64)
        self.assertEqual(tile_geometry(pv, 2, 2, 4)["issued_macs"], 96)
        near = qk | {"layout": "indexed", "key_rows": [{"key_indices": [0, 1], "repetitions": 1}]}
        far = near | {"key_rows": [{"key_indices": [0, 4], "repetitions": 1}]}
        self.assertEqual(work_macs(near), work_macs(far))
        self.assertEqual(tile_geometry(far, 2, 2, 4)["issued_macs"], 2 * tile_geometry(near, 2, 2, 4)["issued_macs"])

    def test_experts_and_grouped_weight_identities(self):
        packed = {"kind": "experts", "tokens_per_expert": [4, 0], "n": 3, "k": 2}
        distributed = packed | {"tokens_per_expert": [3, 1]}
        self.assertEqual(work_macs(packed), work_macs(distributed))
        self.assertEqual(tile_geometry(packed, 4, 3, 2)["issue_requests"], 1)
        self.assertEqual(tile_geometry(distributed, 4, 3, 2)["issue_requests"], 2)
        grouped = {"kind": "grouped", "m": 1, "n": 3, "k": 2, "repetitions": 2}
        self.assertEqual(tile_geometry(grouped, 4, 3, 2)["issue_requests"], 2)

    def test_feedback_timeline(self):
        self.assertEqual(service_cycles({3: 1}, 1, 8, 8, 1)["array_service_cycles"], 24)
        two = service_cycles({3: 2}, 1, 8, 8, 2)
        self.assertEqual(two["raw_wait_cycles"], 12)
        self.assertEqual(two["array_service_cycles"], 25)
        self.assertEqual(service_cycles({3: 8}, 1, 8, 8, 8)["array_service_cycles"], 31)
        self.assertIsNone(service_cycles({2: 1}, 1, 8, None, 8))

    def test_run_length_arithmetic(self):
        for past, tokens, div in [(0, 29, 1), (3, 47, 4), (27, 51, 2)]:
            runs = floor_runs(past, tokens, div, 7)
            self.assertEqual(_stats(runs), (sum(min(t//div, 7) for t in range(past+1, past+tokens+1)), tokens))
            candidates = candidate_runs(past, tokens, div, 2, 4, "pinned_blocks")
            expected = deepseek_v41.candidate_pairs(past, tokens, div, 2, 4)
            self.assertEqual(_stats(candidates), (expected, tokens))


class WorkloadTests(unittest.TestCase):
    def test_v4_reference_replay_per_layer_and_operator(self):
        with patch.dict(sys.modules, {"deepseek_v41": deepseek_v41}):
            from paper.scripts import workloads as historical
        options = read_json(CONFIG / "v4_prefill.json")
        config = read_json(MODEL_ROOT / options["model_id"] / "inference/config.json")
        old = Counter()
        for op in historical.v4_work(config, 0, 256, profile="reference"):
            old[op["layer_id"], op["kernel"]] += op["flops"]
        actual = Counter()
        for op in build_workload(options)["operators"]:
            key, shape = op["operator"], op["shape"]
            if key.startswith(("swa.", "csa.", "hca.")):
                key = "attention." + key.split(".")[-1]
            if key == "index.full_qk":
                key = "index.qk"
            if "execution_length_runs" in shape:
                shape = shape | {"length_runs": shape["execution_length_runs"]}
            actual[op["layer_id"], key] += 2*work_macs(shape)
        self.assertEqual(actual, old)

    def test_v41_replay_global_kv_difference_and_short_decode(self):
        config = read_json(CONFIG / "v41_prefill.json")
        workload = build_workload(config)
        for row in workload["operators"]:
            self.assertEqual(row["useful_macs"], row["historical_macs"], row["op_id"])
        ref = build_workload(config | {"variant": "reference"})
        global_kv = next(row for row in ref["operators"] if row["operator"] == "global_kv.projection"
                         and row["compression_ratio"] == 2)
        self.assertEqual(global_kv["precision_label"], "FP32")
        self.assertEqual(next(row["precision_label"] for row in workload["operators"]
                              if row["op_id"] == global_kv["op_id"]), "BF16")
        rectangular = next(row for row in ref["operators"] if row["operator"] == "index.full_qk")
        self.assertLess(rectangular["useful_macs"], rectangular["historical_macs"])
        decode = build_workload(config | {"stage": "decode", "schedule": "decode", "past_tokens": 32,
                                         "query_tokens": 2})
        self.assertTrue(all(row["query_tokens"] == 1 for row in decode["operators"] if row["layer_id"] >= 0))

    def test_trace_uses_one_histogram_for_all_expert_projections(self):
        options = read_json(CONFIG / "v41_prefill.json") | {"query_tokens": 2}
        base = build_workload(options)
        gate = next(row for row in base["operators"] if row["operator"] == "moe.routed.gate")
        tokens = [2] * 6 + [0] * (len(gate["shape"]["tokens_per_expert"]) - 6)
        observed = build_workload(options, trace={"schema_version": 1, "ops": {
            gate["op_id"]: {"tokens_per_expert": tokens},
        }})
        rows = [row for row in observed["operators"] if row["layer_id"] == gate["layer_id"]
                and row["category"] == "routed_expert"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["shape"]["tokens_per_expert"] == tokens for row in rows))
        self.assertNotEqual(base["workload_id"], observed["workload_id"])


class PrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        area = PACKAGE / "configs/area"
        profiles, _ = import_profiles(read_json(area / "dp_n12_20261112.lock.json"))
        result = enumerate_deployments(profiles, read_json(area / "equal_array.json"))
        cls.deployment = next(row for row in result["deployments"]
                              if row["deployment_id"] == result["baseline_deployment_id"])
        cls.profile = next(row for row in profiles["profiles"] if row["profile_id"] == cls.deployment["profile_id"])
        cls.model = read_json(CONFIG / "serial_local_array.json")

    def test_fixed_deployment_migration_and_incomplete_conversion(self):
        workload = validate_workload(read_json(CONFIG / "synthetic_gemm.json"))
        base = resolve_plan(workload, read_json(CONFIG / "adapter_plan.json"))
        spec = read_json(CONFIG / "synthetic_gemm_fp8.json")
        target = resolve_plan(workload, spec)
        changes = compare_plans(workload, base, target)
        self.assertEqual(changes[0]["useful_macs"], 2805)
        left, = evaluate_workload(workload, base, self.deployment, self.profile, self.model)
        right, = evaluate_workload(workload, target, self.deployment, self.profile, self.model)
        self.assertEqual(left["deployment_id"], right["deployment_id"])
        self.assertEqual(left["useful_macs"], right["useful_macs"])
        self.assertLess(right["shape_utilization"], left["shape_utilization"])
        self.assertIsNotNone(right["gemm_compute_latency_s"])
        spec["rules"][0]["target"]["conversion"] = {"kind": "online"}
        partial, = evaluate_workload(workload, resolve_plan(workload, spec), self.deployment, self.profile, self.model)
        self.assertIsNotNone(partial["array_service_time_s"])
        self.assertIsNone(partial["gemm_compute_latency_s"])
        self.assertIn("conversion_cost_unknown", partial["reasons"])
        self.assertEqual(quality_status(target, [])["status"], "unknown")

    def test_proxy_does_not_implicitly_resolve_w4a8(self):
        workload = build_workload(read_json(CONFIG / "v41_prefill.json") | {"query_tokens": 16})
        plan = resolve_plan(workload, {"schema_version": 1, "name": "proxy",
                                       "format_proxies": {"fp8": "mxfp8_e4m3"}})
        q_down = next(row for row in workload["operators"] if row["operator"] == "q_down")
        expert = next(row for row in workload["operators"] if row["operator"] == "moe.routed.gate")
        self.assertEqual(plan["mappings"][q_down["op_id"]]["proxy_for"], "fp8")
        self.assertIsNone(plan["mappings"][expert["op_id"]]["dp_mode"])

    def test_quality_uses_full_plan_and_exact_threshold(self):
        plan = {"plan_id": "candidate"}
        metric = {"plan_id": "candidate", "metric": "ppl", "direction": "lower",
                  "dataset": "synthetic", "protocol": "synthetic", "model_revision": "fixture",
                  "quantizer_revision": "fixture", "provenance": "synthetic", "reference_value": 1.1,
                  "candidate_value": 1.2, "max_degradation": 0.1}
        self.assertEqual(quality_status(plan, [metric])["status"], "passed")
        self.assertEqual(quality_status(plan, [metric | {"max_degradation": 0.09}])["status"], "failed")
        self.assertEqual(quality_status(plan, [metric | {"plan_id": "other"}])["status"], "unknown")
