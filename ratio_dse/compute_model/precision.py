"""Resolve explicit precision policies and produce workload-preserving plans."""

from decimal import Decimal

from ..common import SCHEMA_VERSION, identity, integer, number, require, versioned
from ..formats import FORMATS, layout

_LABELS = {"BF16": "bf16", "FP16": "fp16", "FP32": "fp32", "FP8": "fp8", "FP4": "fp4"}
_SELECTORS = {"op_id", "operator", "stage", "segment", "category", "subcategory", "layers", "layer_range"}


def _matches(selector, op):
    for key, value in selector.items():
        if key == "layers":
            if op["layer_id"] not in value:
                return False
        elif key == "layer_range":
            if not value[0] <= op["layer_id"] <= value[1]:
                return False
        elif op[key] != value:
            return False
    return True


def _selection(selector):
    require(isinstance(selector, dict) and selector and selector.keys() <= _SELECTORS, "invalid precision selector")
    for key, value in selector.items():
        if key in {"layers", "layer_range"}:
            require(isinstance(value, list) and value and all(type(layer) is int and layer >= -1 for layer in value),
                    f"{key} must contain integer layer IDs")
            if key == "layer_range":
                require(len(value) == 2 and value[0] <= value[1], "layer_range must be [first, last] inclusive")
        else:
            require(isinstance(value, str) and value, f"{key} must be a nonempty string")


def _conversion(value):
    if value is None:
        return {"kind": "unresolved", "cycles_per_operator": None, "bytes_per_operator": None}
    kind = value["kind"]
    require(kind in {"offline", "online", "none"}, "conversion kind must be offline, online or none")
    cycles = value.get("cycles_per_operator")
    amount = value.get("bytes_per_operator")
    if kind in {"offline", "none"}:
        require(cycles in (None, 0) and amount in (None, 0), f"{kind} conversion contributes zero runtime cost")
        cycles, amount = 0, 0
    else:
        if cycles is not None:
            integer("conversion cycles_per_operator", cycles, 0)
        if amount is not None:
            integer("conversion bytes_per_operator", amount, 0)
    return {"kind": kind, "cycles_per_operator": cycles, "bytes_per_operator": amount}


def _mapping(op, bindings):
    label = op["precision_label"]
    if label == "W4A8":
        return {"weight_storage_format": "fp4", "activation_storage_format": "fp8",
                "multiply_a_format": None, "multiply_b_format": None, "accumulator_format": None,
                "scale_format": None, "dp_mode": None, "execution_path": "unresolved_w4a8",
                "conversion": _conversion(None), "precision_basis": "adapter_w4a8_contract", "proxy_for": None}
    fmt = _LABELS.get(label, label.lower())
    resolved = bindings.get(fmt, fmt)
    concrete = resolved in FORMATS
    storage = op.get("weight_storage_hint") or fmt
    conv = _conversion({"kind": "none"}) if storage == fmt else _conversion(None)
    execution_path = "explicit_format_proxy" if fmt in bindings else "native_or_unresolved_format"
    return {"weight_storage_format": storage, "activation_storage_format": fmt,
            "multiply_a_format": resolved, "multiply_b_format": resolved,
            "accumulator_format": ("int32" if resolved == "int8" else "fp32") if concrete or fmt == "fp32" else None,
            "scale_format": layout(resolved)["scale_format"] if concrete else None,
            "dp_mode": resolved if concrete else None,
            "execution_path": execution_path, "conversion": conv,
            "precision_basis": "user_supplied_format_proxy" if fmt in bindings else "adapter",
            "proxy_for": fmt if fmt in bindings else None}


def _target(old, target):
    fmt = target["format_id"]
    require(fmt in FORMATS, f"unknown concrete target format {fmt}")
    storage_a = target.get("activation_storage_format", old["activation_storage_format"])
    storage_b = target.get("weight_storage_format", old["weight_storage_format"])
    path = target["execution_path"]
    require(isinstance(path, str) and path, "target execution_path must be declared")
    same_storage = storage_a == fmt and storage_b == fmt
    conversion = _conversion(target.get("conversion", {"kind": "none"} if same_storage else None))
    if storage_a != fmt or storage_b != fmt:
        require(conversion["kind"] != "none", "storage/multiply mismatch requires a conversion path")
    return {"weight_storage_format": storage_b, "activation_storage_format": storage_a,
            "multiply_a_format": fmt, "multiply_b_format": fmt,
            "accumulator_format": "int32" if fmt == "int8" else "fp32", "scale_format": layout(fmt)["scale_format"],
            "dp_mode": fmt, "execution_path": path, "conversion": conversion, "precision_basis": "user_precision_rule",
            "proxy_for": target.get("proxy_for")}


def resolve_plan(workload, spec):
    """Build a concrete mapping and a traceable list of operators changed by rules."""
    versioned(spec, "precision plan")
    bindings = spec.get("format_proxies", {})
    require(bindings.keys() <= {"fp8", "fp4"}, "only unresolved fp8/fp4 labels accept proxies")
    for label, fmt in bindings.items():
        capacity = "q" if label == "fp8" else "e"
        require(fmt in FORMATS and FORMATS[fmt][:2] == (capacity, int(label[-1]))
                and not fmt.startswith("mxfp6_"), f"{label} proxy must have matching numerical width")
    rows = workload["operators"]
    mappings = {op["op_id"]: _mapping(op, bindings) for op in rows}
    changes, selected = [], set()
    for rule in spec.get("rules", []):
        selector = rule["select"]
        _selection(selector)
        matched = [op for op in rows if _matches(selector, op)]
        require(matched, f"precision selector matched no operators: {selector}")
        for op in matched:
            key = op["op_id"]
            require(key not in selected, f"overlapping precision rules for {key}")
            selected.add(key)
            old = mappings[key]
            source = rule.get("source")
            if source is not None:
                require(source in {op["precision_label"], old["dp_mode"]}, f"{key} source format does not match {source}")
            mappings[key] = _target(old, rule["target"])
            changes.append({"op_id": key, "from_format": old["dp_mode"] or op["precision_label"],
                            "to_format": mappings[key]["dp_mode"], "useful_macs": op["useful_macs"]})
    return {"schema_version": SCHEMA_VERSION, "name": spec["name"],
            "plan_id": identity("precision", [workload["workload_id"], workload["operators"], mappings]),
            "workload_id": workload["workload_id"], "mappings": mappings, "selected_ops": sorted(selected),
            "changes_from_adapter": changes}


def compare_plans(workload, baseline, candidate):
    """Return per-operator changes, including storage- or conversion-only changes."""
    result = []
    for plan in (baseline, candidate):
        require(plan["workload_id"] == workload["workload_id"], "plan does not match workload")
    for op in workload["operators"]:
        key = op["op_id"]
        left, right = baseline["mappings"][key], candidate["mappings"][key]
        if left != right:
            result.append({"op_id": key, "layer_id": op["layer_id"], "operator": op["operator"],
                           "baseline_plan_id": baseline["plan_id"], "candidate_plan_id": candidate["plan_id"],
                           "from_format": left["dp_mode"] or op["precision_label"],
                           "to_format": right["dp_mode"] or op["precision_label"],
                           "useful_macs": op["useful_macs"], "useful_flops": op["useful_flops"],
                           "changed_fields": sorted(key for key in left if left[key] != right[key])})
    return result


def quality_status(plan, records):
    """Quality evidence is evaluated against the complete plan ID."""
    matched = [record for record in records if record["plan_id"] == plan["plan_id"]]
    statuses = []
    for record in matched:
        for key in ("metric", "dataset", "protocol", "model_revision", "quantizer_revision", "provenance"):
            require(isinstance(record[key], str) and record[key], f"quality record requires {key}")
        direction = record["direction"]
        require(direction in {"higher", "lower"}, "quality direction must be higher or lower")
        candidate, reference = record["candidate_value"], record["reference_value"]
        number("candidate_value", candidate, float("-inf"))
        number("reference_value", reference, float("-inf"))
        threshold = number("max_degradation", record["max_degradation"])
        delta = Decimal(str(candidate)) - Decimal(str(reference))
        degradation = delta if direction == "lower" else -delta
        statuses.append(record | {"delta": float(delta), "degradation": float(degradation),
                                  "status": "passed" if degradation <= Decimal(str(threshold)) else "failed"})
    return {"plan_id": plan["plan_id"], "status": ("failed" if any(s["status"] == "failed" for s in statuses)
                                                    else "passed" if statuses else "unknown"),
            "records": statuses}
