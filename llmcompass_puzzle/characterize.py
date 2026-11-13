"""Export N12 evidence, 7 nm proxies and upstream-cost Tensor substitutions."""

import argparse
import csv
import importlib.metadata
import json
import math
from pathlib import Path
import sys

from ratio_dse.area_model import import_profiles
from ratio_dse.common import ROOT, digest, read_json, require
from . import MODEL_VERSION
from .backend import LOCK, baseline_config, chip_area, vector_bundle


def scale_profile(profile, process, clock_hz):
    require(process["proxy_source_node_nm"] == 14 and process["target_node_nm"] == 7,
            "only the explicitly reviewed 14-as-12 to 7 nm proxy is supported")
    require(type(clock_hz) is int and clock_hz > 0, "clock_hz must be a positive integer")
    for key in ("area_divisor", "delay_divisor", "energy_divisor"):
        value = process[key]
        require(type(value) in (int, float) and math.isfinite(value) and value > 0, f"invalid {key}")
    modes = {}
    for fmt, mode in profile["modes"].items():
        dynamic = mode["power_dynamic_w"]
        modes[fmt] = mode | {
            "source_dynamic_w": dynamic, "source_leakage_w": mode["power_leakage_w"],
            "power_dynamic_w": (dynamic * clock_hz / profile["frequency_hz"] / process["energy_divisor"]
                                if dynamic is not None else None),
            "power_leakage_w": None, "power_total_w": None,
            "power_status": "analytical_process_proxy" if dynamic is not None else "missing_evidence",
            "power_reason": "target_leakage_unknown; reference_activity_proxy",
        }
    return profile | {"source_area_um2": profile["area_um2"], "source_frequency_hz": profile["frequency_hz"],
                      "area_um2": profile["area_um2"] / process["area_divisor"], "frequency_hz": clock_hz,
                      "technology_id": "N7_proxy_from_N12_via_14nm", "pvt": None,
                      "status": "analytical_process_proxy", "timing_pass": None, "electrical_pass": None,
                      "source_conditions": {key: profile[key] for key in ("technology_id", "pvt", "clock_gating")},
                      "modes": modes}


def substitute_tensor(config, scaled, shape, extra_mm2_per_sm=0):
    require(len(shape) == 2 and all(type(x) is int and x > 0 for x in shape), "shape must contain two positive integers")
    require(math.isfinite(extra_mm2_per_sm) and extra_mm2_per_sm >= 0, "extra Tensor area must be nonnegative")
    require(config["device"]["frequency_Hz"] == scaled["frequency_hz"], "DP and system clocks must match")
    require(config["device"]["compute_chiplet_count"] == 1, "S1 supports one compute chiplet")
    areas = chip_area(config)
    chip = config["device"]["compute_chiplet"]
    arrays = chip["core"]["sublane_count"]
    dp_per_sm = arrays * shape[0] * shape[1]
    physical, enabled = chip["physical_core_count"], chip["core_count"]
    require(0 < enabled <= physical, "enabled SMs must fit physical SMs")
    replacement = dp_per_sm * scaled["area_um2"] / 1e6 + extra_mm2_per_sm
    removed = areas["core"]["sa_area"]
    total = areas["total_mm2"] + physical * (replacement - removed)
    return {"profile": scaled["profile_id"], "ratio": scaled["ratio_label"],
            "physical_sm_count": physical, "enabled_sm_count": enabled, "physical_dp_shape": list(shape),
            "arrays_per_sm": arrays, "dp_per_sm": dp_per_sm, "physical_dp_count": physical * dp_per_sm,
            "area_model_total_mm2": total, "removed_sa_mm2_per_sm": removed,
            "replacement_tensor_mm2_per_sm": replacement, "extra_tensor_mm2_per_sm": extra_mm2_per_sm,
            "vector_mm2_per_sm": areas["core"]["alu_area"],
            "rf_mm2_per_sm": areas["core"]["regfile_area"], "io_mm2": areas["io_mm2"],
            "peak_tflops_s": {fmt: 2e-12 * enabled * dp_per_sm * mode["native_k"] / mode["ii_cycles"]
                                   * scaled["frequency_hz"] for fmt, mode in scaled["modes"].items()},
            "dp_active_dynamic_proxy_w": {fmt: enabled * dp_per_sm * mode["power_dynamic_w"]
                                          if mode["power_dynamic_w"] is not None else None
                                          for fmt, mode in scaled["modes"].items()},
            "chip_power_w": None, "chip_power_status": "partial_power",
            "status": "analytical_uncalibrated"}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def write_rows(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def run(output, plan_path):
    plan = read_json(plan_path)
    require(plan["schema_version"] == 1 and plan["stage"] == "S1_area_characterization", "expected executable S1 config")
    lock = ROOT / plan["dp_evidence"]
    hardware, evidence = import_profiles(read_json(lock))
    clock = plan["common_clock_hz"]
    baseline = baseline_config(clock_hz=clock)
    require(plan["arrays_per_sm"] == baseline["device"]["compute_chiplet"]["core"]["sublane_count"],
            "S1 keeps the four-array A100 baseline; sublane redesign is not supported")
    reference = chip_area(baseline)
    profiles = [scale_profile(p, plan["process"], clock) for p in hardware["profiles"]]
    rows = []
    for profile in profiles:
        for scale in plan["vector_scales"]:
            row = substitute_tensor(vector_bundle(baseline, scale), profile,
                                    plan["physical_dp_shape"], plan["extra_tensor_mm2_per_sm"])
            row.update(vector_scale=scale, area_budget_mm2=reference["total_mm2"],
                       within_modeled_area_budget=row["area_model_total_mm2"] <= reference["total_mm2"],
                       array_overhead_policy="reuse_baseline_control; explicit_incremental_area_assumption")
            rows.append(row)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "normalized_a100.json", baseline)
    write_json(output / "a100_area_breakdown.json", reference)
    write_json(output / "dp_profiles_7nm_proxy.json", {"schema_version": 1, "process": plan["process"], "profiles": profiles})
    write_rows(output / "tensor_vector_area_candidates.csv", rows)
    source_root = Path(__file__).parent
    sources = [*source_root.glob("*.py"), *ROOT.glob("ratio_dse/area_model/*.py"),
               ROOT / "ratio_dse/common.py", ROOT / "ratio_dse/formats.py"]
    inputs = [plan_path, lock, LOCK, ROOT / "dependencies/deepscaletool.json", *evidence,
              ROOT / "paper/data/process_normalization/table_inputs.json"]
    manifest = {"model_version": MODEL_VERSION, "command": sys.argv, "stage": "S1_area_and_profile_integration",
                "status": "analytical_uncalibrated", "upstream_commit": read_json(LOCK)["commit"],
                "inputs_sha256": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): digest(p) for p in inputs},
                "sources_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
                "outputs_sha256": {p.name: digest(p) for p in output.iterdir()},
                "assumptions": ["N12 uses 14nm DeepScaleTool proxy", "common comparison clock; no N7 timing claim",
                                "upstream physical-area scenario versus 108 enabled SMs", "incremental array overhead is a user scenario",
                                "vector ALU counts and RF ports scale with throughput", "no whole-chip power or inference latency yet"],
                "numpy_version": importlib.metadata.version("numpy")}
    write_json(output / "manifest.json", manifest)
    return {"profiles": len(profiles), "tensor_vector_candidates": len(rows),
            "reference_modeled_area_mm2": reference["total_mm2"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "configs/characterize.json")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output, args.config)))
    except (ValueError, OSError, KeyError, ImportError) as exc:
        parser.exit(2, f"characterize: {exc}\n")


if __name__ == "__main__":
    main()
