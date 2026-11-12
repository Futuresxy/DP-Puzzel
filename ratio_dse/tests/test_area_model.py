import unittest

from ratio_dse.area_model import enumerate_deployments, import_profiles
from ratio_dse.area_model.model import broadcast_vectors
from ratio_dse.common import PACKAGE, read_json
from ratio_dse.formats import layout, vector_bytes

CONFIG = PACKAGE / "configs/area"


class AreaModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hardware, _ = import_profiles(read_json(CONFIG / "dp_n12_20261112.lock.json"))

    def test_current_candidates_and_peaks(self):
        self.assertEqual(len(self.hardware["profiles"]), 9)
        scenario = read_json(CONFIG / "equal_array.json")
        result = enumerate_deployments(self.hardware, scenario)
        self.assertEqual(result["baseline_core_count"], 36)
        self.assertEqual(sum(row["valid"] for row in result["deployments"]), 9)
        rows = {row["profile_id"]: row for row in result["deployments"]}
        self.assertEqual(rows["H16Q32E64"]["unused_area_um2"], 0)
        self.assertEqual(rows["H16Q128E256"]["core_count"], 22)
        self.assertEqual(rows["H16Q128E256"]["per_mode_peak_macs_s"]["mxfp4_e2m1"], 360_448_000_000_000)
        for profile in self.hardware["profiles"]:
            self.assertEqual(profile["modes"]["bf16"]["power_status"], "measured")
            self.assertIsNone(profile["modes"]["nvfp4"]["power_total_w"])

    def test_area_budget_boundaries_and_missing_profile(self):
        source = self.hardware["profiles"][0]
        values = [10.0, 10.000001, 20.000001]
        profiles = [source | {"profile_id": str(i), "area_um2": area} for i, area in enumerate(values)]
        profiles.append({"profile_id": "missing", "area_um2": None, "modes": {},
                         "ratio_label": "unknown", "status": "missing_evidence"})
        scenario = read_json(CONFIG / "equal_array.json") | {
            "baseline_profile": "0", "baseline_cores": 2, "baseline_tensor_fraction": 1,
            "baseline_shape": [1, 1], "legal_shapes": [[1, 1]],
        }
        result = enumerate_deployments({"schema_version": 1, "profiles": profiles}, scenario)
        self.assertEqual([row["core_count"] for row in result["deployments"]], [2, 1, 0, None])
        self.assertEqual([row["valid"] for row in result["deployments"]], [True, True, False, False])
        with self.assertRaisesRegex(ValueError, "tensor_fraction"):
            enumerate_deployments({"schema_version": 1, "profiles": profiles},
                                  scenario | {"baseline_tensor_fraction": 0})

    def test_broadcast_scale_packing_and_bandwidth_gate(self):
        scenario = read_json(CONFIG / "equal_input_bandwidth.json")
        topology = scenario["broadcast_model"]
        self.assertEqual(broadcast_vectors([16, 4], topology), (16, 16))
        self.assertEqual(broadcast_vectors([16, 4], topology | {"share_b_across_row_groups": True}), (16, 4))
        self.assertEqual(vector_bytes(33, layout("mxfp4_e2m1")), (17, 2))
        result = enumerate_deployments(self.hardware, scenario)
        self.assertEqual(len(result["deployments"]), 36)
        by_key = {(r["profile_id"], r["m_array"]): r for r in result["deployments"]}
        base = by_key["H16Q32E64", 16]
        self.assertEqual(base["input_budget_bytes_s"], 32 * 34 * 1e9)
        self.assertTrue(base["valid"])
        big = by_key["H16Q128E256", 16]
        self.assertFalse(big["valid"])
        self.assertIn("input_budget_exceeded:mxfp4_e2m1", big["reasons"])
        self.assertTrue(by_key["H16Q128E256", 4]["valid"])

    def test_locked_evidence_rejects_modified_hash(self):
        lock = read_json(CONFIG / "dp_n12_20261112.lock.json")
        lock["sources"]["dc"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            import_profiles(lock)
