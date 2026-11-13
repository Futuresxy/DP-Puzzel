import copy
import csv
import math
from pathlib import Path
import tempfile
import unittest

from ratio_dse.area_model import import_profiles
from ratio_dse.common import ROOT, read_json
from llmcompass_puzzle.backend import baseline_config, chip_area, vector_bundle
from llmcompass_puzzle.characterize import scale_profile, substitute_tensor
from llmcompass_puzzle.replay import run as replay


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = read_json(ROOT / "llmcompass_puzzle/configs/characterize.json")
        cls.hardware, _ = import_profiles(read_json(ROOT / cls.plan["dp_evidence"]))
        cls.profile = cls.hardware["profiles"][0]

    def test_area_energy_scaling_does_not_invent_leakage_or_timing(self):
        source = copy.deepcopy(self.profile)
        scaled = scale_profile(source, self.plan["process"], 1_000_000_000)
        faster = scale_profile(source, self.plan["process"], 1_132_000_000)
        self.assertEqual(source, self.profile)
        self.assertAlmostEqual(scaled["area_um2"], source["area_um2"] / 7.273)
        self.assertAlmostEqual(scaled["modes"]["bf16"]["power_dynamic_w"],
                               source["modes"]["bf16"]["power_dynamic_w"] / 1.727)
        self.assertAlmostEqual(faster["modes"]["bf16"]["power_dynamic_w"] /
                               scaled["modes"]["bf16"]["power_dynamic_w"], 1.132)
        self.assertIsNone(scaled["modes"]["bf16"]["power_leakage_w"])
        self.assertIsNone(scaled["modes"]["tf32"]["power_dynamic_w"])
        self.assertIsNone(scaled["timing_pass"])
        self.assertEqual(scaled["modes"]["bf16"]["latency_cycles"], 8)

    def test_exact_tensor_replacement_and_enabled_core_accounting(self):
        config = baseline_config()
        io = config["device"]["io"]
        self.assertEqual(io["memory_channel_active_count"] * io["pin_count_per_channel"] * io["bandwidth_per_pin_bit"] / 8, 2039e9)
        self.assertEqual(config["device"]["memory"]["total_capacity_GB"] * 1024**3, 80e9)
        reference = chip_area(config)
        scaled = scale_profile(self.profile, self.plan["process"], 1_000_000_000)
        # Artificial replacement with exactly the removed Tensor area must conserve chip area.
        scaled["area_um2"] = reference["core"]["sa_area"] * 1e6 / 64
        row = substitute_tensor(config, scaled, (4, 4))
        self.assertAlmostEqual(row["area_model_total_mm2"], reference["total_mm2"])
        self.assertAlmostEqual(row["peak_tflops_s"]["bf16"], 221.184)
        config["device"]["compute_chiplet"]["core_count"] = 54
        half = substitute_tensor(config, scaled, (4, 4))
        self.assertEqual(half["area_model_total_mm2"], row["area_model_total_mm2"])
        self.assertEqual(half["peak_tflops_s"]["bf16"] * 2, row["peak_tflops_s"]["bf16"])

    def test_vector_gain_has_alu_and_rf_area_cost(self):
        config = baseline_config()
        before = copy.deepcopy(config)
        baseline = chip_area(config)
        doubled = vector_bundle(config, 2)
        bigger = chip_area(doubled)
        self.assertEqual(config, before)
        self.assertEqual(doubled["device"]["compute_chiplet"]["core"]["vector_unit"]["vector_width"], 32)
        self.assertAlmostEqual(bigger["core"]["alu_area"], 2 * baseline["core"]["alu_area"])
        self.assertGreater(bigger["core"]["regfile_area"], baseline["core"]["regfile_area"])
        self.assertGreater(bigger["total_mm2"], baseline["total_mm2"])

    def test_upstream_scalesim_and_mapper_run_on_cpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = replay(Path(tmp) / "reference")
            with (Path(tmp) / "reference/a100_vector_replay.csv").open() as stream:
                vector = list(csv.DictReader(stream))
        # One OS wave with 16x16x16 takes K+M+N-3 cycles in this pinned scalar backend.
        self.assertEqual(rows[0]["scalar_array_cycles"], 45)
        for row in rows[1:]:
            self.assertTrue(math.isfinite(row["upstream_a100_gemm_seconds"]))
            self.assertGreater(row["upstream_a100_gemm_seconds"], 0)
            self.assertIsNotNone(row["mapping"])
        self.assertEqual(len(vector), 2)
        self.assertTrue(all(math.isfinite(float(r["seconds"])) and float(r["seconds"]) > 0 for r in vector))


if __name__ == "__main__":
    unittest.main()
