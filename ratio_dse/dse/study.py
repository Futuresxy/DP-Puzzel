"""Run the controlled DeepSeek hardware, mapping, precision and power sweeps."""

import argparse
import itertools
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from ..area_model import enumerate_deployments, import_profiles
from ..common import PACKAGE, ROOT, identity, integer, json_text, ratio, read_json, require, versioned, write_run
from ..compute_model import build_workload, resolve_plan
from ..compute_model.workload import MODEL_ROOT, v41
from .model import operator_cost, pareto_indices, tile_groups

BASELINE = "H16Q32E64"
Q = "mxfp8_e4m3"
E = "mxfp4_e2m1"
CATEGORIES = {"attention_core", "attention_projection", "shared_or_dense_ffn", "routed_expert"}
PROJECTIONS = {"q_down", "q_up", "o_final", "window_kv", "swa_kv"}
ATTENTION_PRODUCTS = {"swa.qk", "swa.pv", "csa.qk", "csa.pv"}


def make_cases(config):
    for path in config["workloads"]:
        options = read_json(ROOT / path)
        spans = sorted({(length, 1) for length in config["lengths"]} |
                       {(config["anchor_length"], batch) for batch in config["batches_at_anchor"]})
        for length, batch in spans:
            options = options | {"query_tokens": length, "batch": batch, "variant": "target_native_20261112"}
            workload = build_workload(options)
            yield workload, options


def build_plan(workload, choice):
    """Build one of the original factorial sensitivity plans."""
    expert, grouped, linear, attention = choice
    name = "+".join(filter(None, [
        "expert_fp4" if expert else "expert_fp8",
        "grouped_" + ("fp8" if grouped == Q else "fp4") if grouped else "",
        "linears_fp4" if linear else "", "attention_fp8" if attention else "",
    ]))
    return build_gemm_plan(workload, name, routed_fp4=expert, grouped_format=grouped, shared_fp4=linear,
                           projections_fp4=linear, attention_fp8=attention)


def build_gemm_plan(workload, name, *, routed_fp4=False, grouped_format=None, shared_fp4=False,
                    projections_fp4=False, attention_fp8=False):
    """Resolve operator-specific precision choices at the preformatted local boundary."""
    rules = []
    for op in workload["operators"]:
        operator = op["operator"]
        category = op["category"]
        mode = None
        path = "preformatted_inputs_at_local_boundary"
        weight_storage = None
        if category == "routed_expert":
            mode = E if routed_fp4 else Q
            if not routed_fp4:
                path = "w4a8_materialized_weight_expansion_before_local_boundary"
                weight_storage = "fp4"
        elif operator == "o_group" and grouped_format:
            mode = grouped_format
        elif op["precision_label"] == "FP8" and (
                (projections_fp4 and operator in PROJECTIONS) or (shared_fp4 and operator.startswith("moe.shared."))):
            mode = E
        elif attention_fp8 and operator in ATTENTION_PRODUCTS:
            mode = Q
        if mode is None:
            continue
        rules.append({"select": {"op_id": op["op_id"]}, "target": {
            "format_id": mode, "weight_storage_format": weight_storage or mode,
            "activation_storage_format": mode, "execution_path": path, "conversion": {"kind": "offline"},
        }})
    return resolve_plan(workload, {"schema_version": 1, "name": name, "format_proxies": {"fp8": Q, "fp4": E},
                                   "rules": rules})


def compile_plan(workload, plan):
    """Group identical operations across layers; retain exact multiplicity and GEMM identity."""
    compiled = {}
    excluded = Counter()
    for op in workload["operators"]:
        if op["category"] not in CATEGORIES or op["precision_label"] == "FP32":
            excluded[op["category"], op["precision_label"]] += op["useful_macs"]
            continue
        fmt = plan["mappings"][op["op_id"]]["dp_mode"]
        require(fmt in {"bf16", Q, E}, f"unresolved precision in matched scope: {op['op_id']}")
        key = op["operator"], json_text(op["shape"], compact=True), fmt, op["useful_macs"]
        if key not in compiled:
            compiled[key] = {"operator": op["operator"], "category": op["category"], "fmt": fmt,
                             "shape_key": key[1], "useful_macs": op["useful_macs"],
                             "op_ids": []}
        compiled[key]["op_ids"].append(op["op_id"])
    return list(compiled.values()), excluded


@lru_cache(maxsize=16384)
def _geometry(shape_key, m, n, native_k, partition):
    return tile_groups(json.loads(shape_key), m, n, native_k, partition)


def evaluate(compiled, deployment, profile, settings, detail=False):
    totals = Counter()
    by_operator = defaultdict(Counter)
    shape = deployment["m_array"], deployment["n_array"]
    for op in compiled:
        mode = profile["modes"][op["fmt"]]
        if mode["power_status"] != "measured":
            return None, []
        peak = deployment["per_mode_peak_macs_s"][op["fmt"]]
        geometry, groups = _geometry(op["shape_key"], *shape, mode["native_k"], settings["partition"])
        row = operator_cost(op, geometry, groups, deployment, mode, settings)
        if row is None:
            return None, []
        repeat = len(op["op_ids"])
        row["ideal_s"] = op["useful_macs"] / peak
        for field in ("seconds", "compute_s", "read_s", "write_s", "dp_energy_j", "issued_macs",
                      "ab_bytes", "d_bytes", "useful_macs", "ideal_s", "overlap_s"):
            contribution = row[field] * repeat
            totals[field] += contribution
            if detail:
                by_operator[op["operator"], op["category"], op["fmt"]][field] += contribution
        for field in ("dp_envelope_w", "dp_full_pool_mode_w", "active_cores", "active_arrays",
                      "buffer_required_bytes"):
            totals[field] = max(row[field], totals[field])
        if detail:
            summary = by_operator[op["operator"], op["category"], op["fmt"]]
            summary["instances"] += repeat
            summary["active_arrays_max"] = max(summary["active_arrays_max"], row["active_arrays"])
            summary["active_cores_max"] = max(summary["active_cores_max"], row["active_cores"])
            summary["eligible_arrays"] = row["eligible_arrays"]
            summary["eligible_cores"] = row["eligible_cores"]
            summary["effective_contexts"] = row["effective_contexts"]
            summary["buffer_required_bytes"] = max(summary["buffer_required_bytes"], row["buffer_required_bytes"])
            summary["native_k"] = row["native_k"]
            summary["peak_macs_s_per_local_byte_s"] = row["peak_macs_s_per_local_byte_s"]
    result = dict(totals)
    result["dp_average_w"] = ratio(result["dp_energy_j"], result["seconds"])
    result["local_intensity_macs_byte"] = ratio(result["useful_macs"], result["ab_bytes"] + result["d_bytes"])
    result["geometry_utilization"] = ratio(result["useful_macs"], result["issued_macs"])
    result["local_time_share"] = ratio(result["read_s"] + result["write_s"] - result["overlap_s"], result["seconds"])
    result["effective_tflops_s"] = 2e-12 * result["useful_macs"] / result["seconds"]
    breakdown = [{"operator": op, "category": category, "format_id": fmt, **metrics,
                  "shape_utilization": ratio(metrics["useful_macs"], metrics["issued_macs"]),
                  "local_intensity_macs_byte": ratio(metrics["useful_macs"], metrics["ab_bytes"] + metrics["d_bytes"])}
                 for (op, category, fmt), metrics in sorted(by_operator.items())]
    return result, breakdown


def default_settings(config):
    return {
        "local_tb_s": config["anchor_local_tb_s"], "cap_w": None, "include_local": True,
        "contexts": config["contexts"], "partition": "pooled_output_tiles", "idle_fraction": 0.0,
        "buffer_bytes_per_array": config["buffer_bytes_per_array"], "write_read_ratio": config["write_read_ratio"],
    }


def _case_fields(workload):
    meta = workload["metadata"]
    return {"workload_id": workload["workload_id"], "model": meta["model_id"], "schedule": meta["schedule"],
            "batch": meta["batch"], "tokens": meta["query_tokens"], "routing": meta["routing_policy"]}


def _candidate(label, workload, plan, deployment, profile, settings, compiled, detail=False):
    meta = _case_fields(workload) | {
        "view": label, "profile": profile["profile_id"], "ratio": profile["ratio_label"],
        "topology": deployment["scenario_id"], "deployment_id": deployment["deployment_id"],
        "plan": plan["name"], "plan_id": plan["plan_id"], "quality_status": "unknown",
        "area_mm2": deployment["area_pool_mm2"], "budget_mm2": deployment["area_budget_mm2"],
        "cores": deployment["core_count"], "m_array": deployment["m_array"], "n_array": deployment["n_array"],
        "arrays_per_core": deployment["arrays_per_core"], "local_tb_s": settings["local_tb_s"],
        "cap_w": settings["cap_w"], "contexts": settings["contexts"], "partition": settings["partition"],
        "include_local": settings["include_local"], "idle_fraction": settings["idle_fraction"],
        "activity_scale": settings.get("activity_scale", 1.0),
        "io_schedule": settings.get("io_schedule", "serial"),
        "power_granularity": settings.get("power_granularity", "array"),
        "operand_delivery": settings.get("operand_delivery"),
        "buffer_bytes_per_array": settings["buffer_bytes_per_array"],
        "all_gemm_macs": sum(op["useful_macs"] for op in workload["operators"]),
    }
    key = identity("candidate", meta)
    result, breakdown = evaluate(compiled, deployment, profile, settings, detail)
    meta["candidate_id"] = key
    if result is None:
        return meta | {"status": "infeasible_cap_buffer_or_missing_power"}, []
    return meta | result | {"status": "analytical_uncalibrated",
                            "coverage": ratio(result["useful_macs"], meta["all_gemm_macs"]),
                            "chip_total_energy_j": None, "chip_average_power_w": None,
                            "chip_transient_peak_power_w": None}, [
        {"candidate_id": key, **row} for row in breakdown
    ]


def _record_results(config, deployments, profiles, shared_b):
    anchor = config["anchor_length"], config["anchor_batch"]
    base_settings = default_settings(config)
    base_choice = False, None, False, False
    expert_choice = True, None, False, False
    rows, operators, migrations, exclusions, boundaries = [], [], [], [], []
    main_topology = deployments[0]["scenario_id"]
    for workload, options in make_cases(config):
        is_anchor = (options["query_tokens"], options["batch"]) == anchor
        cases = [row for row in deployments if is_anchor or row["scenario_id"] == main_topology]
        plans = {choice: build_plan(workload, choice) for choice in (base_choice, expert_choice)}
        prepared = {choice: compile_plan(workload, plan) for choice, plan in plans.items()}
        for (category, fmt), macs in prepared[base_choice][1].items():
            exclusions.append(_case_fields(workload) | {"category": category, "precision_label": fmt, "useful_macs": macs})

        def add(view, layout, choice, settings, detail=False):
            if choice not in plans:
                plans[choice] = build_plan(workload, choice)
                prepared[choice] = compile_plan(workload, plans[choice])
            row, op_rows = _candidate(view, workload, plans[choice], layout, profiles[layout["profile_id"]],
                                      settings, prepared[choice][0], detail)
            rows.append(row)
            operators.extend(op_rows)
            return row

        for layout, choice in itertools.product(cases, (base_choice, expert_choice)):
            bandwidths = config["local_read_tb_s_per_core"] if is_anchor else config["workload_sensitivity_tb_s"]
            for bandwidth in bandwidths:
                main_point = is_anchor and bandwidth == config["anchor_local_tb_s"] and layout["scenario_id"] == main_topology
                add("chip_selection", layout, choice, base_settings | {"local_tb_s": bandwidth}, main_point)
            if not is_anchor or layout["scenario_id"] != main_topology:
                continue
            for cap in config["power_caps_w"]:
                add("power_cap", layout, choice, base_settings | {"cap_w": cap})
            for label, change in (
                ("compute_only", {"include_local": False}),
                ("single_context", {"contexts": 1}),
                ("isolated_weights", {"partition": "isolated_weights"}),
                ("idle_10pct", {"idle_fraction": 0.1}),
                ("activity_80pct", {"activity_scale": 0.8}),
                ("activity_120pct", {"activity_scale": 1.2}),
            ):
                add(label, layout, choice, base_settings | change)
            add("shared_b_broadcast", shared_b[layout["profile_id"]], choice, base_settings)

        if not is_anchor:
            continue
        canonical = [layout for layout in cases if layout["scenario_id"] == main_topology]
        for choice in (base_choice, expert_choice):
            coarse = defaultdict(list)
            for row in rows:
                if (row["view"] == "chip_selection" and row["workload_id"] == workload["workload_id"]
                        and row["plan_id"] == plans[choice]["plan_id"] and row["topology"] == main_topology
                        and "seconds" in row):
                    coarse[row["local_tb_s"]].append(row)
            winners = [min(coarse[bw], key=lambda row: (row["seconds"], row["profile"])) for bw in sorted(coarse)]
            for left, right in zip(winners, winners[1:]):
                if left["profile"] == right["profile"]:
                    continue
                lo, hi = left["local_tb_s"], right["local_tb_s"]
                refined = [left]
                subdivisions = config["bandwidth_refinement_subdivisions"]
                for step in range(1, subdivisions):
                    settings = base_settings | {"local_tb_s": lo + (hi - lo) * step / subdivisions}
                    probes = [add("bandwidth_refinement", layout, choice, settings) for layout in canonical]
                    refined.append(min(probes, key=lambda row: (row["seconds"], row["profile"])))
                refined.append(right)
                for a, b in zip(refined, refined[1:]):
                    if a["profile"] != b["profile"]:
                        boundaries.append(_case_fields(workload) | {
                            "plan": a["plan"], "topology": main_topology,
                            "lower_tb_s": a["local_tb_s"], "upper_tb_s": b["local_tb_s"],
                            "lower_ratio": a["ratio"], "upper_ratio": b["ratio"],
                            "lower_candidate_id": a["candidate_id"], "upper_candidate_id": b["candidate_id"],
                        })
        choices = list(itertools.product((False, True), (None, Q, E), (False, True), (False, True)))
        by_id = {op["op_id"]: op for op in workload["operators"]}
        for layout in cases:
            if layout["scenario_id"] != main_topology or layout["profile_id"] not in config["migration_profiles"]:
                continue
            for bandwidth in config["migration_tb_s"]:
                settings = base_settings | {"local_tb_s": bandwidth}
                base = add("model_adaptation", layout, base_choice, settings)
                for choice in choices[1:]:
                    candidate = add("model_adaptation", layout, choice, settings)
                    if "seconds" not in candidate:
                        continue
                    left, right = plans[base_choice], plans[choice]
                    changed = [key for key, mapping in left["mappings"].items()
                               if mapping["dp_mode"] != right["mappings"][key]["dp_mode"]]
                    slack = base["seconds"] - candidate["seconds"]
                    migrations.append(_case_fields(workload) | {
                        "candidate_id": candidate["candidate_id"], "baseline_id": base["candidate_id"],
                        "topology": layout["scenario_id"], "profile": layout["profile_id"], "ratio": layout["ratio_label"],
                        "local_tb_s": bandwidth, "plan": right["name"], "changed_operator_rows": len(changed),
                        "migrated_useful_macs": sum(by_id[key]["useful_macs"] for key in changed),
                        "speedup": base["seconds"] / candidate["seconds"],
                        "energy_ratio": candidate["dp_energy_j"] / base["dp_energy_j"],
                        "conversion_break_even_s": slack,
                        "conversion_break_even_s_per_changed_row": ratio(slack, len(changed)), "quality_status": "unknown",
                    })
        hot = build_workload(options | {"routing_policy": "hot_experts"})
        for choice in (base_choice, expert_choice):
            plan = build_plan(hot, choice)
            packed, omitted = compile_plan(hot, plan)
            if choice == base_choice:
                for (category, fmt), macs in omitted.items():
                    exclusions.append(_case_fields(hot) | {"category": category, "precision_label": fmt, "useful_macs": macs})
            for layout in canonical:
                row, _ = _candidate("hot_experts", hot, plan, layout, profiles[layout["profile_id"]], base_settings, packed)
                rows.append(row)
    return rows, operators, migrations, exclusions, boundaries


def _robustness(rows, topology):
    """Worst-case and median regret across matched workload/bandwidth samples."""
    groups = defaultdict(list)
    for row in rows:
        if row["view"] == "chip_selection" and row["topology"] == topology and "seconds" in row:
            groups[row["workload_id"], row["plan"], row["local_tb_s"]].append(row)
    scores = defaultdict(list)
    for group in groups.values():
        best_t = min(row["seconds"] for row in group)
        best_e = min(row["dp_energy_j"] for row in group)
        for row in group:
            scores[row["plan"], row["ratio"]].append((row["seconds"] / best_t - 1, row["dp_energy_j"] / best_e - 1))
    return [{"plan": plan, "ratio": ratio_label, "topology": topology, "paired_samples": len(values),
             "latency_wins": sum(t == 0 for t, _ in values), "energy_wins": sum(e == 0 for _, e in values),
             "max_latency_regret": max(t for t, _ in values), "max_energy_regret": max(e for _, e in values),
             "median_latency_regret": statistics.median(t for t, _ in values),
             "median_energy_regret": statistics.median(e for _, e in values)}
            for (plan, ratio_label), values in sorted(scores.items())]


def validate_results(rows, migrations, exclusions):
    """Check scope, energy, clock and useful work invariants on the full grid."""
    excluded = Counter()
    for row in exclusions:
        excluded[row["workload_id"]] += row["useful_macs"]
    successful = [row for row in rows if "seconds" in row]
    for row in successful:
        require(row["useful_macs"] <= row["issued_macs"], "issued capacity is below useful work")
        require(row["seconds"] >= row["ideal_s"], "time is below the peak capacity lower bound")
        require(math.isclose(row["seconds"], row["compute_s"] + row["read_s"] + row["write_s"], rel_tol=1e-12),
                "time breakdown disagrees with makespan")
        require(math.isclose(row["dp_average_w"] * row["seconds"], row["dp_energy_j"], rel_tol=1e-12),
                "energy and average power disagree")
        require(row["dp_average_w"] <= row["dp_envelope_w"] + 1e-9, "average exceeds the DP envelope")
        if row["cap_w"] is not None:
            require(row["dp_envelope_w"] <= row["cap_w"] + 1e-9, "DP cap exceeded")
        if row["workload_id"] in excluded:
            require(row["useful_macs"] + excluded[row["workload_id"]] == row["all_gemm_macs"],
                    "selected and excluded useful work do not conserve total GEMM work")
    index = {row["candidate_id"]: row for row in successful}
    require(len(index) == len(successful), "duplicate evaluated candidate ID")
    for migration in migrations:
        left, right = index[migration["baseline_id"]], index[migration["candidate_id"]]
        for key in ("deployment_id", "workload_id", "useful_macs"):
            require(left[key] == right[key], f"precision-only comparison changed {key}")
    def pair(row):
        return tuple(row[key] for key in ("workload_id", "plan_id", "deployment_id", "local_tb_s"))

    baselines = {pair(row): row for row in successful if row["view"] == "chip_selection"}
    schedule_count = 0
    for row in successful:
        if row["view"] in {"compute_only", "single_context", "isolated_weights"}:
            baseline = baselines[pair(row)]
            for key in ("useful_macs", "issued_macs", "ab_bytes", "d_bytes"):
                require(row[key] == baseline[key], f"schedule ablation changed {key}")
            schedule_count += 1
    return {"schema_version": 1, "status": "passed_analytical_invariants", "cases_checked": len(successful),
            "fixed_deployment_migrations_checked": len(migrations), "schedule_pairs_checked": schedule_count,
            "hardware_accuracy": "uncalibrated"}


def _comparisons(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["status"] == "analytical_uncalibrated" and row["view"] in {"chip_selection", "power_cap", "model_adaptation"}:
            key = tuple(row[k] for k in ("view", "model", "tokens", "batch", "local_tb_s", "cap_w"))
            key += ((row["topology"], row["profile"]) if row["view"] == "model_adaptation" else (row["plan"],))
            groups[key].append(row)
    selection, pareto = [], []
    for candidates in groups.values():
        objectives = (("fastest", "seconds"), ("lowest_energy", "dp_energy_j"),
                      ("lowest_average_power", "dp_average_w"), ("lowest_envelope", "dp_envelope_w"))
        for label, metric in objectives:
            winner = min(candidates, key=lambda row: (row[metric], row["candidate_id"]))
            selection.append(winner | {"selection": label, "candidate_count": len(candidates),
                                       "ties": sum(row[metric] == winner[metric] for row in candidates)})
        for label, fields in (
            ("area_envelope_time", ("area_mm2", "dp_envelope_w", "seconds")),
            ("area_energy_time", ("area_mm2", "dp_energy_j", "seconds")),
        ):
            for index in pareto_indices(candidates, fields):
                pareto.append(candidates[index] | {"objective_set": label})
    return selection, pareto


def _columns(rows):
    return list(dict.fromkeys(key for row in rows for key in row))


def run(config_path, output, command):
    config = versioned(read_json(config_path), "DSE study")
    for field in ("local_read_tb_s_per_core", "workload_sensitivity_tb_s", "migration_tb_s"):
        values = config[field]
        require(values and len(values) == len(set(values)) and min(values) > 0, f"{field} requires unique positive rates")
    require(config["anchor_local_tb_s"] in config["local_read_tb_s_per_core"],
            "anchor bandwidth must appear in local_read_tb_s_per_core")
    integer("bandwidth_refinement_subdivisions", config["bandwidth_refinement_subdivisions"], 2)
    lock_path = ROOT / config["evidence"]
    hardware, locked = import_profiles(read_json(lock_path))
    profiles = {p["profile_id"]: p for p in hardware["profiles"]}
    deployments = []
    for path in config["topologies"]:
        scenario = read_json(ROOT / path)
        data = enumerate_deployments(hardware, scenario)
        deployments.extend(row for row in data["deployments"] if row["valid"])
    require(len(deployments) == len(profiles) * len(config["topologies"]), "study requires one valid layout per profile")
    main = read_json(ROOT / config["topologies"][0])
    broadcast = main["broadcast_model"] | {"share_b_across_row_groups": True}
    reuse_scenario = main | {"scenario_id": main["scenario_id"] + "_shared_b", "broadcast_model": broadcast}
    shared_b = {row["profile_id"]: row for row in enumerate_deployments(hardware, reuse_scenario)["deployments"]
                if row["valid"]}
    rows, operators, migrations, exclusions, boundaries = _record_results(config, deployments, profiles, shared_b)
    validation = validate_results(rows, migrations, exclusions)
    robustness = _robustness(rows, deployments[0]["scenario_id"])
    selection, pareto = _comparisons(rows)
    inputs = [config_path, lock_path, *locked, *(ROOT / path for path in config["topologies"] + config["workloads"])]
    for path in config["workloads"]:
        model = read_json(ROOT / path)["model_id"]
        inputs.append(MODEL_ROOT / model / "inference/config.json")
    tables = {"candidate_evaluations.csv": rows, "operator_breakdown.csv": operators,
              "precision_migrations.csv": migrations, "excluded_work.csv": exclusions,
              "selection_summary.csv": selection, "pareto.csv": pareto,
              "bandwidth_boundaries.csv": boundaries, "robustness.csv": robustness}
    summary = ("# DeepSeek analytical DSE\n\n"
               f"{len(rows)} candidate evaluations over {len(profiles)} measured DP profiles. "
               "The modeled boundary is matched Attention/MoE GEMMs at local ingress and egress. "
               "Mode measurements use Qwen3-8B replay activity. Energy and power are conditional DP proxies. "
               "Precision quality is unknown. See the study report for controlled comparisons.\n")
    sources = [v41.__file__, *PACKAGE.glob("area_model/*.py"), *PACKAGE.glob("compute_model/*.py")]
    write_run(output, model="dse", command=command, inputs=inputs, config=config,
              documents={"validation.json": validation,
                         "study.json": {"schema_version": 1, "deployment_count": len(deployments),
                                         "candidate_count": len(rows), "power_scope": "dp_activity_proxy",
                                         "memory_scope": "per_core_local_ingress_and_egress"}},
              tables={name: (data, _columns(data)) for name, data in tables.items()},
              summary=summary, extra_sources=sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PACKAGE / "configs/dse/deepseek_study.json")
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)
    try:
        run(args.config, args.output, ["python3.11", "-m", "ratio_dse.dse.study", *argv])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"study: {exc}\n")


if __name__ == "__main__":
    main()
