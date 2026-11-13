"""Command-line entry point for the area model."""

import argparse
import sys
from pathlib import Path

from ..common import read_json, write_run
from . import enumerate_deployments, import_profiles


def run(args, command):
    source = args.evidence or args.profiles
    if args.evidence:
        hardware, extra_inputs = import_profiles(read_json(source))
    else:
        hardware, extra_inputs = read_json(source), []
    scenario = read_json(args.scenario)
    deployment = enumerate_deployments(hardware, scenario)
    profiles, rows = hardware["profiles"], deployment["deployments"]
    mode_rows = [{"profile_id": p["profile_id"], **mode} for p in profiles for mode in p["modes"].values()]
    deployment_modes = [{"deployment_id": row["deployment_id"], "format_id": fmt, **metrics,
                         "pool_peak_tflops_s": (2e-12 * metrics["pool_peak_macs_s"]
                                                if metrics.get("pool_peak_macs_s") is not None else None)}
                        for row in rows for fmt, metrics in row["modes"].items()]
    missing = ([{"profile_id": p["profile_id"], "status": p["status"], "reason": p.get("reason", p["status"])}
                for p in profiles if p["status"] != "valid"]
               + [{"profile_id": row["profile_id"], "format_id": row["format_id"],
                   "status": row["power_status"], "reason": row.get("power_reason")}
                  for row in mode_rows if row["power_status"] != "measured"])
    base = next(row for row in rows if row["deployment_id"] == deployment["baseline_deployment_id"])
    summary = ("# DP deployments\n\n"
               f"Scenario `{scenario['scenario_id']}` yielded {sum(row['valid'] for row in rows)} "
               f"valid deployments out of {len(rows)}. The baseline has {deployment['baseline_core_count']} "
               f"units of kind `{base['core_kind']}`, each with {base['subcores_per_core']} subcores, "
               f"{base['tensorcores_per_subcore']} TensorCores per subcore, and {base['dp_per_core']} DP total.\n\n"
               "Each peak refers to a single mode occupying the declared resource pool. Area and peak "
               "are analytical estimates using single-DP synthesis evidence. The input budget refers to the "
               "local source of A/B data. DP power measurements use the activity window in each mode profile.\n")
    write_run(args.output, model="area_model", command=command, inputs=[source, args.scenario, *extra_inputs],
              config=scenario, documents={"hardware_profiles.json": hardware, "deployments.json": deployment,
                                          "missing_evidence.json": {"schema_version": 1, "entries": missing}},
              tables={
                  "profile_modes.csv": (mode_rows, ["profile_id", "format_id", "native_k", "latency_cycles",
                                                     "ii_cycles", "macs_per_cycle", "accumulator_format",
                                                     "power_dynamic_w", "power_leakage_w", "power_total_w",
                                                     "power_status", "power_reason", "power_run_id"]),
                  "deployments.csv": (rows, ["deployment_id", "scenario_id", "profile_id", "ratio_label",
                                              "core_kind", "subcores_per_core", "tensorcores_per_subcore",
                                              "m_array", "n_array", "arrays_per_core", "dp_per_tensorcore",
                                              "dp_per_subcore", "dp_per_core", "core_count",
                                              "frequency_hz", "area_tensor_um2_per_core",
                                              "area_peripheral_um2_per_core", "area_core_um2", "area_pool_um2",
                                              "area_pool_mm2", "area_budget_um2", "unused_area_um2",
                                              "input_budget_bytes_s", "valid", "reasons"]),
                  "deployment_modes.csv": (deployment_modes, ["deployment_id", "format_id", "status", "native_k",
                                                                "core_peak_macs_s", "pool_peak_macs_s",
                                                                "pool_peak_tflops_s", "a_input_bytes_s",
                                                                "b_input_bytes_s", "input_bytes_s",
                                                                "input_budget_headroom_bytes_s",
                                                                "dp_d_stream_bytes_s_per_core",
                                                                "ab_one_issue_working_set_bytes_per_core",
                                                                "saturation_feasible"]),
              }, summary=summary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--evidence", type=Path, help="locked DP evidence JSON")
    source.add_argument("--profiles", type=Path, help="normalized HardwareProfile JSON")
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)
    try:
        run(args, ["python3.11", "-m", "ratio_dse.area_model", *argv])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"area_model: {exc}\n")


if __name__ == "__main__":
    main()
