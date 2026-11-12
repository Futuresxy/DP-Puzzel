"""Build a GEMM ledger and optionally compare plans on an area deployment."""

import argparse
import sys
from collections import Counter
from pathlib import Path

from ..common import digest, read_json, require, versioned, write_run
from . import build_workload, compare_plans, evaluate_workload, resolve_plan, validate_workload
from .precision import quality_status
from .workload import MODEL_ROOT, reference_diff, v41

OP_COLUMNS = ["op_id", "stage", "segment", "layer_id", "operator", "category", "subcategory",
              "shape_kind", "m", "n", "k", "repetitions", "precision_label", "useful_macs",
              "useful_flops", "historical_macs", "dependencies", "source_basis"]
MAP_COLUMNS = ["precision_plan_id", "op_id", "precision_label", "weight_storage_format",
               "activation_storage_format", "multiply_a_format", "multiply_b_format", "accumulator_format",
               "scale_format", "dp_mode", "execution_path", "conversion", "precision_basis", "proxy_for", "useful_macs"]
EVAL_COLUMNS = ["workload_id", "precision_plan_id", "op_id", "deployment_id", "status", "reasons", "dp_mode",
                "native_k", "ii_cycles", "latency_cycles", "useful_macs", "issued_macs",
                "padding_or_masked_macs", "redundant_logical_macs", "shape_utilization", "k_tail_utilization",
                "temporal_utilization", "effective_utilization", "issue_intervals_cycles", "raw_wait_cycles",
                "drain_cycles", "array_service_cycles", "local_transfer_cycles", "conversion_cycles",
                "conversion_bytes", "ideal_compute_lower_bound_s", "array_service_time_s",
                "gemm_compute_latency_s", "bytes_by_interface", "calibration_status"]
DIFF_METRICS = ("issued_macs", "shape_utilization", "array_service_cycles", "local_transfer_cycles",
                "conversion_cycles", "gemm_compute_latency_s")
CHANGE_COLUMNS = ["op_id", "layer_id", "operator", "baseline_plan_id", "candidate_plan_id", "from_format",
                  "to_format", "useful_macs", "useful_flops", "changed_fields", "baseline_status",
                  "candidate_status", *["delta_" + metric for metric in DIFF_METRICS], "delta_bytes_by_interface"]


def _load(args):
    if args.workload:
        require(not (args.model_config or args.trace), "model config and trace require a model scenario")
        workload = validate_workload(read_json(args.workload))
        return workload, [], [args.workload], {"workload_id": workload["workload_id"]}, []
    options = read_json(args.scenario)
    config = args.model_config or MODEL_ROOT / options["model_id"] / "inference/config.json"
    trace = read_json(args.trace) if args.trace else None
    default = build_workload(options, config_path=config)
    workload = default if trace is None else build_workload(options, config_path=config, trace=trace)
    other = ("reference" if options["variant"] == "target_native_20261112" else "target_native_20261112")
    alternate = build_workload(options | {"variant": other}, config_path=config)
    sources = [v41.__file__] if workload["metadata"]["adapter"] == "v41" else []
    return (workload, reference_diff(default, alternate), [args.scenario, config] + ([args.trace] if trace else []),
            options, sources)


def _hardware(args):
    require(bool(args.area_run) == bool(args.array_model), "array evaluation needs --area-run and --array-model")
    require(not args.deployment_id or args.area_run, "--deployment-id requires --area-run")
    if not args.area_run:
        return None, []
    profiles_path = args.area_run / "hardware_profiles.json"
    deployments_path = args.area_run / "deployments.json"
    paths = [profiles_path, deployments_path]
    manifest_path = args.area_run / "manifest.json"
    if manifest_path.exists():
        manifest = versioned(read_json(manifest_path), "area manifest")
        require(manifest["model"] == "area_model", "--area-run manifest must describe area_model")
        for path in paths:
            require(manifest["outputs_sha256"].get(path.name) == digest(path), f"area output SHA-256 mismatch: {path}")
        paths.append(manifest_path)
    hardware = versioned(read_json(profiles_path), "hardware profiles")
    deployments = versioned(read_json(deployments_path), "deployments")
    key = args.deployment_id or deployments["baseline_deployment_id"]
    deployment = next((row for row in deployments["deployments"] if row["deployment_id"] == key), None)
    require(deployment is not None and deployment["valid"], f"unknown or infeasible deployment {key}")
    profile = next(row for row in hardware["profiles"] if row["profile_id"] == deployment["profile_id"])
    model = versioned(read_json(args.array_model), "array evaluation scenario")
    return (deployment, profile, model), [*paths, args.array_model]


def _plan_tables(workload, plans, evaluation):
    total = sum(op["useful_macs"] for op in workload["operators"])
    summaries, exclusions, mappings, metrics = [], [], [], []
    for plan in plans:
        plan_id = plan["plan_id"]
        groups = Counter()
        evaluated = resolved = 0
        for op in workload["operators"]:
            key = op["op_id"]
            mapping = plan["mappings"][key]
            result = evaluation.get((plan_id, key), {})
            fmt = mapping["dp_mode"] or op["precision_label"]
            status = result.get("status")
            if not status:
                status = "mode_resolved" if mapping["dp_mode"] else "unresolved"
                if mapping["multiply_a_format"] == "fp32":
                    status = "unsupported"
            groups[(op["category"], op["subcategory"], fmt, status)] += op["useful_macs"]
            resolved += op["useful_macs"] if mapping["dp_mode"] else 0
            evaluated += op["useful_macs"] if result.get("gemm_compute_latency_s") is not None else 0
            mappings.append(dict(mapping, op_id=key, precision_plan_id=plan_id,
                                 precision_label=op["precision_label"], useful_macs=op["useful_macs"]))
            if op["category"] == "residual_gemm" or status in {"unsupported", "unresolved", "partial"}:
                exclusions.append({"precision_plan_id": plan_id, "op_id": key, "category": op["category"],
                                   "status": status, "format_id": fmt, "useful_macs": op["useful_macs"],
                                   "reason": result.get("reasons") or
                                   (["residual_gemm"] if op["category"] == "residual_gemm" else [status])})
        metrics.append({"precision_plan_id": plan_id, "name": plan["name"], "all_gemm_useful_macs": total,
                        "mode_resolved_useful_macs": resolved,
                        "array_completion_covered_useful_macs": evaluated if evaluation else None,
                        "mode_resolved_fraction": resolved / total if total else None,
                        "array_completion_fraction": evaluated / total if total and evaluation else None})
        for (category, subcategory, fmt, status), macs in sorted(groups.items()):
            summaries.append({"precision_plan_id": plan_id, "category": category, "subcategory": subcategory,
                              "format_id": fmt, "status": status, "useful_macs": macs, "useful_flops": 2*macs,
                              "all_gemm_useful_macs": total, "share_of_all_gemm": macs / total if total else None})
    return summaries, exclusions, mappings, metrics


def _comparisons(workload, plans, evaluation):
    changes = []
    for plan in plans[1:]:
        for row in compare_plans(workload, plans[0], plan):
            left = evaluation.get((row["baseline_plan_id"], row["op_id"]), {})
            right = evaluation.get((row["candidate_plan_id"], row["op_id"]), {})
            row.update(baseline_status=left.get("status"), candidate_status=right.get("status"))
            for metric in DIFF_METRICS:
                a, b = left.get(metric), right.get(metric)
                row["delta_" + metric] = b - a if a is not None and b is not None else None
            a_io, b_io = left.get("bytes_by_interface", {}), right.get("bytes_by_interface", {})
            row["delta_bytes_by_interface"] = {key: b_io[key] - a_io[key] for key in a_io.keys() & b_io.keys()
                                               if a_io[key] is not None and b_io[key] is not None} or None
            changes.append(row)
    return changes


def run(args, command):
    workload, references, inputs, config, extra_sources = _load(args)
    hardware, hardware_paths = _hardware(args)
    plan_specs = [read_json(path) for path in args.plan] if args.plan else [{"schema_version": 1, "name": "adapter"}]
    plans = [resolve_plan(workload, spec) for spec in plan_specs]
    require(len({plan["plan_id"] for plan in plans}) == len(plans), "duplicate resolved precision plans")
    records = versioned(read_json(args.quality), "quality evidence")["records"] if args.quality else []
    quality = [quality_status(plan, records) for plan in plans]
    evaluations = []
    if hardware:
        for plan in plans:
            evaluations.extend(evaluate_workload(workload, plan, *hardware))
        config = dict(config, deployment_id=hardware[0]["deployment_id"], array_model=hardware[2])
    lookup = {(row["precision_plan_id"], row["op_id"]): row for row in evaluations}
    summary_rows, exclusions, mappings, metrics = _plan_tables(workload, plans, lookup)
    ledger = []
    for row in workload["operators"]:
        shape = row["shape"]
        ledger.append(row | {key: shape.get(key) for key in ("m", "n", "k", "repetitions")}
                      | {"shape_kind": shape["kind"]})
    descriptors = {name: {op["op_id"]: op["shape"] for op in workload["operators"] if op["shape"]["kind"] == kind}
                   for name, kind in (("sparse_shapes.json", "ragged"), ("expert_histograms.json", "experts"))}
    services = []
    ops = {op["op_id"]: op for op in workload["operators"]}
    for row in evaluations:
        if row["issued_macs"] is not None:
            services.append({key: row.get(key) for key in (
                "workload_id", "precision_plan_id", "deployment_id", "op_id", "dp_mode", "native_k",
                "tiles_by_k_steps", "ii_cycles", "latency_cycles", "context_slots", "feedback_cycles",
                "array_service_cycles", "bytes_by_interface", "conversion_cycles", "status", "reasons")}
                | {"dependencies": ops[row["op_id"]]["dependencies"]})
    summary = ("# GEMM workload and precision plans\n\n"
               f"Workload `{workload['workload_id']}` has {len(ledger)} operator records and "
               f"{sum(op['useful_macs'] for op in ledger):,} useful MAC.\n\n"
               "Metrics cover the declared GEMM scope. An array evaluation covers one array from "
               "local ingress through local output under its configured dataflow. See the coverage "
               "and reason fields for missing inputs or unresolved modes. The first plan is the comparison baseline.\n")
    documents = {"workload.json": workload,
                 "precision_plans.json": {"schema_version": 1, "plans": plans},
                 "quality_records.json": {"schema_version": 1, "plans": quality},
                 "coverage.json": {"schema_version": 1, "plans": metrics},
                 "tile_services.json": {"schema_version": 1, "services": services},
                 "backend_validation.json": {"schema_version": 1, "backend": "analytical",
                                             "calibration_status": "analytical_uncalibrated",
                                             "reference_systolic": {"status": "disabled", "reason": "no pinned adaptation"},
                                             "verification_command": "python3.11 -m unittest discover -s ratio_dse/tests"},
                 **{name: {"schema_version": 1, "operators": rows} for name, rows in descriptors.items()}}
    write_run(args.output, model="compute_model", command=command, config=config,
              inputs=[*inputs, *hardware_paths, *args.plan, *([args.quality] if args.quality else [])],
              documents=documents, extra_sources=extra_sources, summary=summary,
              tables={
                  "gemm_ledger.csv": (ledger, OP_COLUMNS),
                  "precision_map.csv": (mappings, MAP_COLUMNS),
                  "reference_diff.csv": (references, ["op_id", "changes", "current_precision", "alternate_precision",
                                                     "current_useful_macs", "alternate_useful_macs",
                                                     "current_historical_macs", "alternate_historical_macs"]),
                  "workload_summary.csv": (summary_rows, ["precision_plan_id", "category", "subcategory", "format_id",
                                                         "status", "useful_macs", "useful_flops", "all_gemm_useful_macs",
                                                         "share_of_all_gemm"]),
                  "excluded_work.csv": (exclusions, ["precision_plan_id", "op_id", "category", "status", "format_id",
                                                    "useful_macs", "reason"]),
                  "operator_evaluations.csv": (evaluations, EVAL_COLUMNS),
                  "precision_migrations.csv": (_comparisons(workload, plans, lookup), CHANGE_COLUMNS),
              })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--scenario", type=Path, help="DeepSeek workload scenario JSON")
    source.add_argument("--workload", type=Path, help="normalized workload JSON")
    parser.add_argument("--model-config", type=Path, help="override the registered model config")
    parser.add_argument("--trace", type=Path, help="optional sparse/expert observations JSON")
    parser.add_argument("--plan", action="append", type=Path, default=[], help="repeat to compare plans against the first")
    parser.add_argument("--quality", type=Path, help="optional external full-plan quality JSON")
    parser.add_argument("--area-run", type=Path, help="output directory of the area model")
    parser.add_argument("--deployment-id", help="evaluate this deployment instead of the scenario baseline")
    parser.add_argument("--array-model", type=Path, help="array dataflow, feedback and interface scenario")
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    argv = sys.argv[1:] if argv is None else argv
    try:
        run(parser.parse_args(argv), ["python3.11", "-m", "ratio_dse.compute_model", *argv])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"compute_model: {exc}\n")


if __name__ == "__main__":
    main()
