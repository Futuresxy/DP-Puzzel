"""Select the fastest measured DP profile for each DeepSeek precision plan."""

import argparse
import sys
from collections import Counter
from itertools import product
from pathlib import Path

from ..area_model import enumerate_deployments, import_profiles
from ..common import PACKAGE, ROOT, number, read_json, require, versioned, write_run
from ..compute_model import build_workload
from ..compute_model.precision import quality_status
from ..compute_model.workload import MODEL_ROOT, v41
from .study import BASELINE, E, Q, _candidate, _columns, build_gemm_plan, build_plan, compile_plan, default_settings

STAGED_LABELS = (("baseline", "Base"), ("step1", "O-down + experts"),
                 ("step2", "+ projections"), ("step3", "+ attention"))
_STEP1 = {"grouped_format": E, "routed_fp4": True, "shared_fp4": True}
_STEP2 = _STEP1 | {"projections_fp4": True}
_STAGED_CHOICES = ({}, _STEP1, _STEP2, _STEP2 | {"attention_fp8": True})


def _plans(workload, plan_set):
    if plan_set == "staged":
        for (name, _), choice in zip(STAGED_LABELS, _STAGED_CHOICES):
            yield build_gemm_plan(workload, name, **choice)
    else:
        for choice in product((False, True), (None, Q, E), (False, True), (False, True)):
            yield build_plan(workload, choice)


def _select(candidates):
    valid = sorted((row for row in candidates if "seconds" in row),
                   key=lambda row: (row["seconds"], row["ratio"]))
    if not valid:
        return {"feasible_profiles": 0, "status": "no_feasible_profile"}
    best = valid[0]
    second = valid[1] if len(valid) > 1 else None
    baseline = next((row for row in valid if row["profile"] == BASELINE), None)
    least_energy = min(valid, key=lambda row: (row["dp_energy_j"], row["ratio"]))
    return {
        "status": best["status"], "feasible_profiles": len(valid),
        "winner_ratio": best["ratio"], "winner_candidate_id": best["candidate_id"], "winner_time_s": best["seconds"],
        "winner_dp_energy_j": best["dp_energy_j"], "winner_dp_envelope_w": best["dp_envelope_w"],
        "runner_up_ratio": second["ratio"] if second else None,
        "runner_up_time_s": second["seconds"] if second else None,
        "runner_up_gap_pct": (second["seconds"] / best["seconds"] - 1) * 100 if second else None,
        "baseline_ratio": baseline["ratio"] if baseline else None,
        "baseline_time_s": baseline["seconds"] if baseline else None,
        "baseline_slowdown_pct": (baseline["seconds"] / best["seconds"] - 1) * 100 if baseline else None,
        "energy_winner_ratio": least_energy["ratio"], "min_dp_energy_j": least_energy["dp_energy_j"],
        "coverage": best["coverage"],
    }


def _add_step_comparison(row, prior):
    """Expose the additional serial online time a migration can tolerate."""
    if not prior:
        return
    row["previous_plan_id"] = prior["plan_id"]
    row["previous_candidate_id"] = prior["candidate_id"]
    if "seconds" in prior and "seconds" in row:
        row["fixed_profile_conversion_headroom_s"] = prior["seconds"] - row["seconds"]


def _step_moves(workload, previous, plan):
    if previous is None:
        return []
    changes = Counter()
    for op in workload["operators"]:
        key = op["op_id"]
        source = previous["mappings"][key]["dp_mode"]
        target = plan["mappings"][key]["dp_mode"]
        if source != target:
            changes[op["operator"], source, target] += op["useful_macs"]
    return [{"operator": op, "from_format": source, "to_format": target, "useful_macs": macs}
            for (op, source, target), macs in sorted(changes.items())]


def run(config_path, output, caps_w, command, *, plan_set="staged", quality_path=None):
    require(plan_set in {"staged", "factorial"}, "unknown precision plan set")
    config = versioned(read_json(config_path), "DSE study")
    caps = [None, *[number("DP cap (W)", cap, minimum=1e-9) for cap in caps_w]]
    require(len(caps) == len(set(caps)), "DP caps must be unique")
    rates = config["local_read_tb_s_per_core"]
    require(rates and len(rates) == len(set(rates)) and min(rates) > 0, "local bandwidths must be unique and positive")

    lock = ROOT / config["evidence"]
    topology_path = ROOT / config["topologies"][0]
    hardware, locked_inputs = import_profiles(read_json(lock))
    profiles = {p["profile_id"]: p for p in hardware["profiles"]}
    scenario = read_json(topology_path)
    deployments = enumerate_deployments(hardware, scenario)["deployments"]
    require(len(deployments) == len(profiles) and all(row["valid"] for row in deployments),
            "expected one area-feasible deployment for each measured profile")

    settings = default_settings(config)
    inputs = [config_path, lock, topology_path, *locked_inputs]
    quality_records = []
    if quality_path is not None:
        quality_records = versioned(read_json(quality_path), "quality evidence")["records"]
        inputs.append(quality_path)
    candidates, selections, plan_records, moves = [], [], [], []
    for path in config["workloads"]:
        path = ROOT / path
        options = read_json(path) | {"query_tokens": config["anchor_length"], "batch": config["anchor_batch"],
                                     "variant": "target_native_20261112"}
        inputs.extend([path, MODEL_ROOT / options["model_id"] / "inference/config.json"])
        workload = build_workload(options)
        modeled_total = None
        previous_plan = None
        previous_by_point = {}
        for plan in _plans(workload, plan_set):
            quality = quality_status(plan, quality_records)
            plan_records.append({"workload_id": workload["workload_id"], "model": options["model_id"],
                                 "plan": plan["name"], "plan_id": plan["plan_id"], "quality": quality})
            step_moves = _step_moves(workload, previous_plan, plan)
            if step_moves:
                moves.extend({"workload_id": workload["workload_id"], "model": options["model_id"],
                              "plan": plan["name"], "plan_id": plan["plan_id"],
                              "previous_plan_id": previous_plan["plan_id"], **move} for move in step_moves)
            compiled, _ = compile_plan(workload, plan)
            counts = Counter()
            for op in compiled:
                counts[op["fmt"]] += op["useful_macs"] * len(op["op_ids"])
            total = sum(counts.values())
            require(total > 0, "empty matched GEMM workload")
            if modeled_total is None:
                modeled_total = total
            require(total == modeled_total, "precision migration changed useful MACs")
            current_by_point = {}
            for bandwidth, cap in product(rates, caps):
                matched = []
                point = settings | {"local_tb_s": bandwidth, "cap_w": cap}
                previous = previous_by_point.get((bandwidth, cap), {})
                prior_rows = previous.get("candidates", {})
                for layout in deployments:
                    profile = profiles[layout["profile_id"]]
                    row, _ = _candidate("migration_selection", workload, plan, layout, profile, point, compiled)
                    row["quality_status"] = quality["status"]
                    _add_step_comparison(row, prior_rows.get(layout["profile_id"]))
                    if "seconds" in row:
                        require(row["useful_macs"] == total, "modeled evaluation changed useful MACs")
                        require(cap is None or row["dp_envelope_w"] <= cap + 1e-9, "DP envelope exceeds cap")
                    matched.append(row)
                candidates.extend(matched)
                selected = {
                    "workload_id": workload["workload_id"], "model": options["model_id"], "schedule": options["schedule"],
                    "tokens": options["query_tokens"], "batch": options["batch"], "topology": scenario["scenario_id"],
                    "plan": plan["name"], "plan_id": plan["plan_id"], "local_tb_s": bandwidth, "cap_w": cap,
                    "bf16_macs": counts["bf16"], "mxfp8_macs": counts[Q], "mxfp4_macs": counts[E],
                    "fp4_share_pct": 100 * counts[E] / total, "useful_macs": total, "quality_status": quality["status"],
                } | _select(matched)
                if previous:
                    prior = previous["selection"]
                    selected.update(previous_plan_id=prior["plan_id"], previous_winner_ratio=prior.get("winner_ratio"))
                    if "winner_time_s" in selected and "winner_time_s" in prior:
                        selected["reselected_conversion_headroom_s"] = prior["winner_time_s"] - selected["winner_time_s"]
                        winner = next(row for row in matched if row["candidate_id"] == selected["winner_candidate_id"])
                        selected["winner_fixed_profile_conversion_headroom_s"] = winner.get("fixed_profile_conversion_headroom_s")
                selections.append(selected)
                if plan_set == "staged":
                    current_by_point[bandwidth, cap] = {"candidates": {row["profile"]: row for row in matched},
                                                         "selection": selected}
            if plan_set == "staged":
                previous_plan = plan
                previous_by_point = current_by_point
    summary = ("# DeepSeek precision migration and chip selection\n\n"
               f"{len(candidates)} profile evaluations in {len(selections)} matched comparisons. "
               "Every comparison holds model, plan, topology, bandwidth and DP budget fixed while ranking profiles. "
               "GEMM timing uses preformatted local inputs. Quality status is reported separately. "
               "Headroom in the staged scan is the maximum extra serial online conversion time before a step breaks even.\n")
    screened = [row for row in selections if row["quality_status"] == "passed" and "winner_ratio" in row]
    tables = {"candidate_evaluations.csv": (candidates, _columns(candidates)),
              "selections.csv": (selections, _columns(selections)),
              "quality_screened_selections.csv": (screened, _columns(selections))}
    if plan_set == "staged":
        tables["step_moves.csv"] = (moves, ["workload_id", "model", "plan", "plan_id", "previous_plan_id",
                                            "operator", "from_format", "to_format", "useful_macs"])
    checks = {"schema_version": 1, "profile_evaluations": len(candidates), "matched_comparisons": len(selections),
              "profiles_per_comparison": len(profiles), "invariants": ["useful_mac_conservation", "dp_envelope_cap"]}
    write_run(output, model="dse", command=command, inputs=inputs,
              config=config | {"migration_selection_caps_w": caps, "migration_plan_set": plan_set},
              documents={"validation.json": checks, "quality_records.json": {"schema_version": 1, "plans": plan_records}},
              tables=tables,
              summary=summary, extra_sources=[v41.__file__, *PACKAGE.glob("area_model/*.py"), *PACKAGE.glob("compute_model/*.py")])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PACKAGE / "configs/dse/deepseek_study.json")
    parser.add_argument("--caps-w", type=float, nargs="*", default=[150, 250],
                        help="DP power caps to probe in addition to the uncapped case")
    parser.add_argument("--plan-set", choices=("staged", "factorial"), default="staged")
    parser.add_argument("--quality", type=Path, help="optional full-plan quality records")
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)
    try:
        run(args.config, args.output, args.caps_w, ["python3.11", "-m", "ratio_dse.dse.migration_selection", *argv],
            plan_set=args.plan_set, quality_path=args.quality)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"migration_selection: {exc}\n")


if __name__ == "__main__":
    main()
