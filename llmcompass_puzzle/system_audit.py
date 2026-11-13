"""Reproduce resource opportunity costs; not a DeepSeek latency search."""

import argparse
import copy
import json
import math
from pathlib import Path

from ratio_dse.area_model import import_profiles
from ratio_dse.common import ROOT, digest, read_json, require
from .backend import LOCK, baseline_config, chip_area, vector_bundle
from .characterize import scale_profile, substitute_tensor, write_json, write_rows
from .system_contract import evaluate_power_windows, quantization_work


def run(output):
    output = output.resolve()
    require(not output.exists(), "output must be a new directory")
    config_path = ROOT / "llmcompass_puzzle/configs/characterize.json"
    config = read_json(config_path)
    evidence_path = ROOT / config["dp_evidence"]
    hardware, evidence = import_profiles(read_json(evidence_path))
    baseline = baseline_config(clock_hz=config["common_clock_hz"])
    require(config["arrays_per_sm"] == 4, "audit uses the four-array S1 organization")
    upstream_area = chip_area(baseline)
    budget = upstream_area["total_mm2"]
    profiles = [scale_profile(p, config["process"], config["common_clock_hz"]) for p in hardware["profiles"]]
    rows = []
    for profile in profiles:
        for scale in (0.5, 1, 2):
            design = vector_bundle(baseline, scale)
            fixed = substitute_tensor(design, profile, config["physical_dp_shape"], config["extra_tensor_mm2_per_sm"])
            # Upstream compute + crossbar area is linear in physical SM count.
            per_sm = (fixed["area_model_total_mm2"] - fixed["io_mm2"]) / 128
            physical = min(256, math.floor((budget - fixed["io_mm2"]) / per_sm / 8) * 8)
            require(physical >= 8, "no eight-SM group fits the budget")
            design["device"]["compute_chiplet"]["physical_core_count"] = physical
            enabled = math.floor(physical * 108 / 128)
            design["device"]["compute_chiplet"]["core_count"] = enabled
            fitted = substitute_tensor(design, profile, config["physical_dp_shape"], config["extra_tensor_mm2_per_sm"])
            require(fitted["area_model_total_mm2"] <= budget + 1e-8, "area fit exceeds budget")
            require(physical == 256 or fitted["area_model_total_mm2"] + 8 * per_sm > budget, "fit not maximal")
            rows.append({"ratio": profile["ratio_label"], "vector_scale": scale,
                         "fixed_128_sm_area_mm2": fixed["area_model_total_mm2"],
                         "budget_mm2": budget, "fitted_physical_sms": physical, "fitted_enabled_sms": enabled,
                         "fitted_area_mm2": fitted["area_model_total_mm2"],
                         "fitted_bf16_tflops": fitted["peak_tflops_s"]["bf16"],
                         "fitted_mxfp4_tflops": fitted["peak_tflops_s"]["mxfp4_e2m1"],
                         "fitted_vector_tflops": enabled * 512 * scale * config["common_clock_hz"] / 1e12,
                         "dp_dynamic_proxy_w": fitted["dp_active_dynamic_proxy_w"],
                         "chip_power_status": "unknown", "inference_latency_s": None})
    anchor = next(p for p in profiles if p["ratio_label"] == "1:2:4")
    first = substitute_tensor(baseline, anchor, config["physical_dp_shape"], config["extra_tensor_mm2_per_sm"])
    area_parts = {"tensor": first["replacement_tensor_mm2_per_sm"] * 128,
                  "vector_alu": upstream_area["core"]["alu_area"] * 128,
                  "register_file": upstream_area["core"]["regfile_area"] * 128,
                  "sm_sram": upstream_area["core"]["local_buffer_area"] * 128,
                  "sm_control": upstream_area["core"]["control_area"] * 128,
                  "core_interconnect": upstream_area["compute_parts"]["crossbar_area"],
                  **upstream_area["io_parts"]}
    area_parts.pop("total_die_area")
    require(math.isclose(sum(area_parts.values()), first["area_model_total_mm2"]), "area parts do not conserve total")
    changes = []
    for label, field, value in (("one_more_physical_HBM_channel", "memory_channel_physical_count", 7),
                                ("double_physical_L2", "physical_global_buffer_MB", 96)):
        design = copy.deepcopy(baseline)
        design["device"]["io"][field] = value
        changes.append({"scenario": label, "added_area_mm2": chip_area(design)["total_mm2"] - budget,
                        "scope": "area sensitivity only; active resources and timing unchanged"})
    # Deliberately artificial coefficients exercise contracts, not hardware calibration.
    recipe = {"kind": "block_local", "status": "synthetic_contract_example", "vector_work_per_value": 3,
              "special_work_per_block": 2, "pack_work_per_word": 1}
    conversions = {fmt: {mode: quantization_work(2, 33, fmt, recipe, fused_producer=mode == "fused",
                                                producer_allows_fusion=mode == "fused")
                         for mode in ("standalone", "fused")}
                   for fmt in ("mxfp8_e4m3", "mxfp4_e2m1")}
    power_profile = {"boundary": "device_including_hbm", "status": "synthetic_contract_example",
                     "base_w": [10, 10], "dynamic_j_per_event": {"matrix": [2, 2], "vector": [1, 1], "hbm": [0.5, 0.5]}}
    windows = [{"duration_s": 1, "events": {"matrix": 20, "vector": 10, "hbm": 20}},
               {"duration_s": 9, "events": {}}]
    power = evaluate_power_windows(windows, power_profile, 60, "device_including_hbm")
    output.mkdir(parents=True)
    write_rows(output / "area_fitted_resources.csv", rows)
    write_json(output / "resource_observations.json", {"baseline_ratio": anchor["ratio_label"],
               "total_area_mm2": first["area_model_total_mm2"], "area_components_mm2": area_parts,
               "area_component_percent": {k: 100 * v / first["area_model_total_mm2"] for k, v in area_parts.items()},
               "memory_area_sensitivities": changes,
               "baseline_peak_hbm_balance_flop_per_byte": {k: v * 1e12 / 2039e9 for k, v in first["peak_tflops_s"].items()}})
    write_json(output / "contract_examples.json", {"status": "synthetic_not_hardware_measurement",
               "quantization": conversions, "power": power})
    sources = [*Path(__file__).parent.glob("*.py"), *ROOT.glob("ratio_dse/area_model/*.py"),
               ROOT / "ratio_dse/common.py", ROOT / "ratio_dse/formats.py"]
    inputs = [config_path, evidence_path, LOCK, *evidence]
    write_json(output / "manifest.json", {"stage": "system_resource_audit", "inference_simulated": False,
               "inputs_sha256": {str(p.relative_to(ROOT)): digest(p) for p in inputs},
               "sources_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
               "output_sha256": {p.name: digest(p) for p in output.iterdir()},
               "clock_hz": config["common_clock_hz"],
               "assumptions": ["fixed shape, clock, SRAM, HBM and L2 except named area probes",
                               "physical SM groups of eight, at most 256; enabled fraction held at 108/128",
                               "vector issue, ALU counts and RF ports use S1 resource bundles",
                               "N12-to-7nm proxy and incremental Tensor area from executable S1 config",
                               "no calibrated full-system power; example power coefficients are synthetic",
                               "peak balance points are roofline diagnostics, not measured traffic or latency"]})
    return {"area_fitted_candidates": len(rows), "budget_mm2": budget, "full_system_timing": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output)))


if __name__ == "__main__":
    main()
