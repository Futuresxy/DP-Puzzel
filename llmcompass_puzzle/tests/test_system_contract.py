import copy
import unittest

from llmcompass_puzzle.system_contract import evaluate_power_windows, quantization_work


RECIPE = {"kind": "block_local", "status": "synthetic_test_only",
          "vector_work_per_value": 3, "special_work_per_block": 2, "pack_work_per_word": 1}
POWER = {"boundary": "device_including_hbm", "status": "synthetic_test_only", "base_w": [10, 10],
         "dynamic_j_per_event": {"matrix_issue": [2, 2], "vector_work": [1, 1], "hbm_byte": [0.5, 0.5]}}


class SystemContractTests(unittest.TestCase):
    def test_block_tail_and_metadata_are_per_row(self):
        row = quantization_work(2, 33, "mxfp4_e2m1", RECIPE)
        self.assertEqual((row["blocks"], row["source_read_bytes"], row["output_payload_bytes"],
                          row["output_scale_bytes"]), (4, 132, 34, 4))
        self.assertEqual(row["work"], {"vector_work": 208, "special_work": 8})

    def test_fusion_saves_traffic_not_conversion_work(self):
        base = quantization_work(2, 33, "mxfp4_e2m1", RECIPE)
        fused = quantization_work(2, 33, "mxfp4_e2m1", RECIPE, fused_producer=True, producer_allows_fusion=True)
        self.assertEqual(base["work"], fused["work"])
        self.assertEqual(fused["source_read_bytes"], 0)
        self.assertEqual(fused["replaced_producer_write_bytes"], 132)
        self.assertEqual(fused["extra_launches"], 0)
        shared = quantization_work(2, 33, "mxfp4_e2m1", RECIPE, fused_producer=True,
                                   producer_allows_fusion=True, keep_high_precision_output=True)
        self.assertEqual(shared["replaced_producer_write_bytes"], 0)
        with self.assertRaises(ValueError):
            quantization_work(2, 33, "mxfp4_e2m1", RECIPE, fused_producer=True)

    def test_8_to_4_is_not_a_second_full_quantizer(self):
        q = quantization_work(2, 32, "mxfp8_e4m3", RECIPE)
        e = quantization_work(2, 32, "mxfp4_e2m1", RECIPE)
        self.assertEqual(q["blocks"], e["blocks"])
        self.assertEqual(q["work"]["special_work"], e["work"]["special_work"])
        self.assertEqual(q["output_payload_bytes"], 2 * e["output_payload_bytes"])
        self.assertEqual(q["output_scale_bytes"], e["output_scale_bytes"])

    def test_short_power_violation_is_not_hidden_by_long_idle(self):
        result = evaluate_power_windows([
            {"duration_s": 1, "events": {"matrix_issue": 20, "vector_work": 10, "hbm_byte": 20}},
            {"duration_s": 9, "events": {}}], POWER, 60, "device_including_hbm")
        self.assertEqual(result["peak_window_power_w"], [70, 70])
        self.assertEqual(result["energy_j"], [160, 160])
        self.assertFalse(result["admitted"])
        self.assertEqual(result["status"], "infeasible")

    def test_missing_power_is_unknown_and_overlap_sums(self):
        result = evaluate_power_windows([{"duration_s": 1, "events": {"matrix_issue": 10, "unmeasured": 1}}],
                                        POWER, 60, "device_including_hbm")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["energy_j"], [30, None])
        self.assertFalse(result["admitted"])
        required = copy.deepcopy(POWER)
        required["required_event_keys"] = ["matrix_issue", "vector_work", "hbm_byte"]
        omitted = evaluate_power_windows([{"duration_s": 1, "events": {"matrix_issue": 1}}], required,
                                        60, "device_including_hbm")
        self.assertEqual(omitted["status"], "unknown")
        both = evaluate_power_windows([{"duration_s": 1, "events": {"matrix_issue": 10, "vector_work": 20}}],
                                      POWER, 40, "device_including_hbm")
        self.assertFalse(both["admitted"])
        with self.assertRaises(ValueError):
            evaluate_power_windows([{"duration_s": 1, "events": {}}], POWER, 40, "die")

    def test_interval_uncertainty_and_fixed_work_energy(self):
        profile = copy.deepcopy(POWER)
        profile["dynamic_j_per_event"]["matrix_issue"] = [2, 4]
        fast = evaluate_power_windows([{"duration_s": 1, "events": {"matrix_issue": 10}}], profile, 40, "device_including_hbm")
        slow = evaluate_power_windows([{"duration_s": 2, "events": {"matrix_issue": 10}}], profile, 40, "device_including_hbm")
        self.assertEqual(fast["status"], "uncertain")
        self.assertTrue(slow["admitted"])
        self.assertEqual(slow["energy_j"], [40, 60])  # same dynamic work, twice base energy


if __name__ == "__main__":
    unittest.main()
