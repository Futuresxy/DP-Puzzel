"""Joint DP ratio, array shape and precision-plan search under explicit budgets."""

import argparse
import sys
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

from ..area_model import enumerate_deployments, import_profiles
from ..common import PACKAGE, ROOT, integer, number, read_json, require, versioned, write_run
from ..compute_model import build_workload
from ..compute_model.workload import MODEL_ROOT, v41
from .migration_selection import _plans, _step_moves
from .model import pareto_indices
from .study import E, Q, _candidate, _columns, compile_plan, default_settings


def construct_deployments(hardware, baseline, shapes, bandwidth):
    """Keep the same baseline area calibration in both construction experiments."""
    layouts = []
    for construction in ("equal_array", "equal_input_bandwidth"):
        scenario = baseline | {
            "scenario_id": f"joint_{construction}_{bandwidth:g}TBs",
            "constraint_kind": construction, "input_budget_bytes_s": bandwidth * 1e12,
            "legal_shapes": [baseline["baseline_shape"]] if construction == "equal_array" else shapes,
        }
        layouts.extend(enumerate_deployments(hardware, scenario)["deployments"])
    fill = defaultdict(float)
    for layout in layouts:
        layout["bandwidth_utilization_at_full_issue"] = max(
            layout["modes"][fmt]["input_bytes_s"] / (bandwidth * 1e12)
            for fmt in baseline["supported_format_set"])
        if layout["valid"] and layout["constraint_kind"] == "equal_input_bandwidth":
            key = layout["profile_id"]
            fill[key] = max(fill[key], layout["bandwidth_utilization_at_full_issue"])
    for layout in layouts:
        layout["bandwidth_filled"] = (
            layout["valid"] and layout["constraint_kind"] == "equal_input_bandwidth"
            and abs(layout["bandwidth_utilization_at_full_issue"] - fill[layout["profile_id"]]) < 1e-12)
    return layouts


def select_designs(rows):
    """Select latency and DP-energy minima; preserve a separate Pareto set."""
    valid = sorted((row for row in rows if "seconds" in row),
                   key=lambda row: (row["seconds"], row["dp_energy_j"], row["candidate_id"]))
    if not valid:
        return {"status": "no_feasible_candidate", "feasible_candidates": 0}, []
    best = valid[0]
    least_energy = min(valid, key=lambda row: (row["dp_energy_j"], row["seconds"], row["candidate_id"]))
    selected = {"status": "analytical_uncalibrated", "feasible_candidates": len(valid),
                "winner_candidate_id": best["candidate_id"], "winner_ratio": best["ratio"],
                "winner_plan": best["plan"], "winner_shape": [best["m_array"], best["n_array"]],
                "winner_cores": best["cores"], "winner_dp_count": best["installed_dp_count"],
                "winner_active_cores_max": best["active_cores"],
                "winner_time_s": best["seconds"], "winner_effective_tflops_s": best["effective_tflops_s"],
                "winner_dp_energy_j": best["dp_energy_j"], "winner_dp_envelope_w": best["dp_envelope_w"],
                "winner_bandwidth_utilization_at_full_issue": best["bandwidth_utilization_at_full_issue"],
                "runner_up_gap_pct": (valid[1]["seconds"] / best["seconds"] - 1) * 100 if len(valid) > 1 else None,
                "energy_winner_candidate_id": least_energy["candidate_id"],
                "minimum_dp_energy_j": least_energy["dp_energy_j"], "coverage": best["coverage"]}
    frontier = [valid[index] for index in pareto_indices(valid, ("area_mm2", "seconds", "dp_envelope_w"))]
    return selected, frontier


def run(config_path, output, command):
    config = versioned(read_json(config_path), "joint search config")
    require(config["quality_policy"] == "out_of_scope", "this search treats precision plans as supplied inputs")
    require(config["bandwidth_scope"] == "per_core_local_input", "only per-core local bandwidth is modeled")
    require(config["power_granularity"] in ("core", "array"), "unknown power granularity")
    require(config["operand_delivery"] == "native_issue_width", "declare the buffer-to-DP port assumption")
    rates = config["local_read_tb_s_per_core"]
    caps = config["power_caps_w"]
    schedules = config["io_schedules"]
    for values in (rates, caps, schedules):
        require(values and len(values) == len(set(values)), "search axes must be nonempty and unique")
    for bandwidth in rates:
        require(number("local bandwidth", bandwidth) > 0, "local bandwidth must be positive")
    for cap in caps:
        if cap is not None:
            number("DP power cap", cap)
    require(set(schedules) <= {"serial", "single_buffer", "pingpong"}, "unknown I/O schedule")
    integer("contexts", config["contexts"])
    integer("buffer_bytes_per_array", config["buffer_bytes_per_array"])
    require(number("write_read_ratio", config["write_read_ratio"]) > 0, "write bandwidth must be positive")
    lock = ROOT / config["evidence"]
    topology = ROOT / config["baseline_topology"]
    baseline = read_json(topology)
    require(baseline["constraint_kind"] == "equal_array", "baseline must fix array shape")
    require(baseline["broadcast_model"]["a_temporal_reuse"] == baseline["broadcast_model"]["b_temporal_reuse"] == 1,
            "cross-request residency requires an identity-aware schedule; temporal reuse must be one")
    hardware, locked_inputs = import_profiles(read_json(lock))
    profiles = {profile["profile_id"]: profile for profile in hardware["profiles"]}
    deployments = {bandwidth: construct_deployments(hardware, baseline, config["legal_shapes"], bandwidth)
                   for bandwidth in rates}
    areas = {layout["area_budget_um2"] for layouts in deployments.values() for layout in layouts}
    require(len(areas) == 1, "construction experiments must share one area budget")
    settings = default_settings(config) | {"power_granularity": config["power_granularity"],
                                          "operand_delivery": config["operand_delivery"]}
    inputs = [config_path, lock, topology, *locked_inputs]
    candidates, plans, moves, excluded = [], [], [], []
    evaluation_inputs = {}
    for workload_path in config["workloads"]:
        path = ROOT / workload_path
        options = read_json(path) | {"query_tokens": config["anchor_length"], "batch": config["anchor_batch"],
                                     "variant": "target_native_20261112"}
        workload = build_workload(options)
        inputs.extend([path, MODEL_ROOT / options["model_id"] / "inference/config.json"])
        previous = None
        conserved = None
        for plan in _plans(workload, "staged"):
            compiled, omissions = compile_plan(workload, plan)
            counts = Counter()
            for op in compiled:
                counts[op["fmt"]] += op["useful_macs"] * len(op["op_ids"])
            total = sum(counts.values())
            require(total > 0 and (conserved is None or total == conserved), "migration must conserve useful MACs")
            conserved = total
            plans.append({"workload_id": workload["workload_id"], "model": options["model_id"],
                          "plan": plan["name"], "plan_id": plan["plan_id"], "quality_policy": "out_of_scope",
                          "bf16_macs": counts["bf16"], "mxfp8_macs": counts[Q], "mxfp4_macs": counts[E],
                          "useful_macs": total})
            moves.extend({"workload_id": workload["workload_id"], "plan": plan["name"], **move}
                         for move in _step_moves(workload, previous, plan))
            excluded.extend({"workload_id": workload["workload_id"], "plan": plan["name"],
                             "category": category, "precision": precision, "useful_macs": macs}
                            for (category, precision), macs in omissions.items())
            previous = plan
            for bandwidth, cap, schedule in product(rates, caps, schedules):
                point = settings | {"local_tb_s": bandwidth, "cap_w": cap, "io_schedule": schedule}
                for layout in deployments[bandwidth]:
                    if not layout["valid"]:
                        continue
                    row, _ = _candidate("joint_search", workload, plan, layout,
                                        profiles[layout["profile_id"]], point, compiled)
                    row.update(quality_status="out_of_scope", construction=layout["constraint_kind"],
                               bandwidth_filled=layout["bandwidth_filled"],
                               bandwidth_utilization_at_full_issue=layout["bandwidth_utilization_at_full_issue"],
                               installed_dp_count=layout["dp_per_core"] * layout["core_count"],
                               local_input_port_sum_tb_s=layout["core_count"] * bandwidth,
                               per_mode_peak_tflops_s={fmt: peak * 2e-12 if peak is not None else None
                                                      for fmt, peak in layout["per_mode_peak_macs_s"].items()})
                    if "seconds" in row:
                        require(row["useful_macs"] == total, "candidate changed useful MACs")
                        require(cap is None or row["dp_envelope_w"] <= cap + 1e-9, "DP cap exceeded")
                        require(row["buffer_required_bytes"] <= settings["buffer_bytes_per_array"], "buffer exceeded")
                        require(abs(row["seconds"] - row["compute_s"] - row["read_s"] - row["write_s"]
                                    + row["overlap_s"]) < 1e-8, "timeline accounting mismatch")
                    candidates.append(row)
                    evaluation_inputs[row["candidate_id"]] = workload, plan, layout, point, compiled

    forward_groups, reverse_groups = defaultdict(list), defaultdict(list)
    for row in candidates:
        axes = tuple(row[key] for key in ("workload_id", "model", "local_tb_s", "cap_w", "io_schedule"))
        views = (["equal_array"] if row["construction"] == "equal_array" else
                 ["bandwidth_feasible"] + (["bandwidth_filled"] if row["bandwidth_filled"] else []))
        for view in views:
            forward_groups[(*axes, row["plan"], view)].append(row)
        reverse_groups[(*axes, row["deployment_id"])].append(row)
    forward, reverse, frontier = [], [], []
    common_keys = ("workload_id", "model", "local_tb_s", "cap_w", "io_schedule")
    for key, rows in forward_groups.items():
        fields = dict(zip((*common_keys, "plan", "construction_view"), key))
        best, pareto = select_designs(rows)
        forward.append(fields | best)
        frontier.extend(fields | {"candidate_id": row["candidate_id"], "area_mm2": row["area_mm2"],
                                  "seconds": row["seconds"], "dp_envelope_w": row["dp_envelope_w"]} for row in pareto)
    # Emit empty cohorts too (e.g. no full-rate shape can fit a small bandwidth budget).
    present = set(forward_groups)
    for plan in plans:
        for bandwidth, cap, schedule, view in product(rates, caps, schedules,
                                                     ("equal_array", "bandwidth_feasible", "bandwidth_filled")):
            key = (plan["workload_id"], plan["model"], bandwidth, cap, schedule, plan["plan"], view)
            if key not in present:
                forward.append(dict(zip((*common_keys, "plan", "construction_view"), key)) | select_designs([])[0])
    for key, rows in reverse_groups.items():
        best, _ = select_designs(rows)
        reverse.append(dict(zip((*common_keys, "deployment_id"), key)) | best)
    operators = []
    winner_ids = {row["winner_candidate_id"] for row in forward if "winner_candidate_id" in row}
    for candidate_id in sorted(winner_ids):
        workload, plan, layout, point, compiled = evaluation_inputs[candidate_id]
        _, breakdown = _candidate("joint_search", workload, plan, layout,
                                  profiles[layout["profile_id"]], point, compiled, detail=True)
        operators.extend(breakdown)
    tables = {name: (rows, _columns(rows)) for name, rows in (
        ("candidate_evaluations.csv", candidates), ("workload_to_hardware.csv", forward),
        ("hardware_to_migration.csv", reverse), ("pareto.csv", frontier),
        ("precision_workloads.csv", plans), ("step_moves.csv", moves), ("excluded_work.csv", excluded),
        ("winning_operator_breakdown.csv", operators))}
    validation = {"schema_version": 1, "candidate_evaluations": len(candidates),
                  "feasible_evaluations": sum("seconds" in row for row in candidates),
                  "workload_to_hardware_groups": len(forward), "hardware_to_migration_groups": len(reverse),
                  "quality_policy": "out_of_scope", "area_budget_um2": next(iter(areas)),
                  "invariants": ["fixed_area_budget", "useful_mac_conservation", "dp_power_cap",
                                 "buffer_capacity", "timeline_accounting"]}
    summary = ("# Joint hardware and precision-plan search\n\n"
               f"{len(candidates)} evaluations; {len(forward)} workload-to-hardware cohorts; "
               f"{len(reverse)} hardware-to-migration cohorts.\n\n"
               "Precision plans are supplied scenarios; model quality is out of scope. All times are analytical, "
               "uncalibrated GEMM completion times at the preformatted local-input boundary.\n\n"
               "Equal-array candidates may stall on input. Bandwidth-feasible candidates meet the full-rate "
               "input bound for every configured format. Bandwidth-filled candidates maximize that bound's "
               "utilization among legal shapes of the same DP profile; tied shapes remain candidates. "
               "Runtime power and tiling may favor a smaller shape, so both shape views are reported.\n\n"
               "Core power allocation keeps all installed DP leakage. Single/ping-pong buffers use K-round "
               "banks, explicit fill/RAW/drain and serial output writeback; independent bank refill/issue ports "
               "are assumed. No cross-request A/B residency, HBM, DVFS, SRAM/uncore power or online conversion "
               "is included. Per-core peripheral area is fixed to the baseline; buffer/port/interconnect "
               "implementation costs and expanded-array timing need calibration.\n")
    write_run(output, model="dse", command=command, inputs=inputs, config=config,
              documents={"validation.json": validation,
                         "deployments.json": {"schema_version": 1, "deployments":
                                              [row for layouts in deployments.values() for row in layouts]}},
              tables=tables, summary=summary,
              extra_sources=[v41.__file__, *PACKAGE.glob("area_model/*.py"), *PACKAGE.glob("compute_model/*.py")])
    return validation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PACKAGE / "configs/dse/joint_search.json")
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)
    try:
        print(run(args.config, args.output, ["python3.11", "-m", "ratio_dse.dse.joint_search", *argv]))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"joint_search: {exc}\n")


if __name__ == "__main__":
    main()
