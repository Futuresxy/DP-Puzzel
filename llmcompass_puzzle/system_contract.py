"""Small system-DSE primitives: conversion work and windowed power admission.

No timing model or unmeasured power coefficient is supplied implicitly.
"""

import math

from ratio_dse.common import require
from ratio_dse.formats import layout, vector_bytes


def nonnegative(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            f"{name} must be finite and nonnegative")
    return value


def quantization_work(rows, columns, target_format, recipe, *, fused_producer=False,
                      producer_allows_fusion=False, keep_high_precision_output=False):
    """BF16 -> block-scaled low precision, once per unique tensor representation.

    Coefficients count abstract work, not literal ISA instructions. They must be
    calibrated together with the matching vector/special-function service rates.
    Fused output is still materialized; consumer/register fusion is not assumed.
    Only a one-pass block-local recipe is supported, not global current scaling.
    NVFP4 assumes a calibrated, fixed per-tensor scale (4 metadata bytes), with
    online group16 scales. A dynamic tensor-wide scale requires another model.
    """
    require(type(rows) is int and rows > 0 and type(columns) is int and columns > 0,
            "positive integer tensor dimensions required")
    require(target_format in ("mxfp8_e4m3", "mxfp4_e2m1", "nvfp4"), "unsupported block quantization target")
    require(recipe["kind"] == "block_local", "only block-local quantization is modeled")
    require(not fused_producer or producer_allows_fusion, "fusion requires a legal producer edge")
    coefficients = {key: nonnegative(recipe[key], key) for key in
                    ("vector_work_per_value", "special_work_per_block", "pack_work_per_word")}
    spec = layout(target_format)
    blocks = rows * math.ceil(columns / spec["scale_block_elements"])
    values = rows * columns
    words = rows * math.ceil(columns * spec["element_slot_bits"] / 32)
    payload, metadata = vector_bytes(columns, spec)
    source_bytes = values * 2
    return {
        "values": values, "blocks": blocks, "target_format": target_format,
        "work": {"vector_work": values * coefficients["vector_work_per_value"]
                 + words * coefficients["pack_work_per_word"],
                 "special_work": blocks * coefficients["special_work_per_block"]},
        "source_read_bytes": 0 if fused_producer else source_bytes,
        "output_payload_bytes": rows * payload,
        "output_scale_bytes": rows * metadata + (4 if target_format == "nvfp4" else 0),
        "replaced_producer_write_bytes": source_bytes if fused_producer and not keep_high_precision_output else 0,
        "extra_launches": 0 if fused_producer else 1,
        "minimum_block_scratch_bytes": 2 * min(columns, spec["scale_block_elements"]),
        "coefficient_status": recipe["status"], "latency_s": None,
        "traffic_scope": "logical tensor bytes; mapper must assign memory level and transaction alignment",
    }


def interval(value, name):
    if value is None:
        return None
    require(isinstance(value, (tuple, list)) and len(value) == 2, f"{name} requires [lower, upper]")
    lo, hi = (nonnegative(v, name) for v in value)
    require(lo <= hi, f"invalid interval: {name}")
    return lo, hi


def evaluate_power_windows(windows, profile, cap_w, boundary):
    """Admit only traces whose full modeled-window upper bound fits the cap.

    Windows partition a schedule; counts include ALL concurrent engines. A
    coefficient is J/event and base_w covers installed-resource idle/static
    power at this design and clock. Dynamic events count incremental energy
    above that base. Missing active coefficients never become zero power.
    This is a window-average cap, not an electrical transient/droop simulator.
    """
    require(windows, "nonempty schedule required")
    require(boundary in ("die", "device_including_hbm"), "explicit power boundary required")
    require(boundary == profile["boundary"], "power profile and cap boundaries differ")
    require(nonnegative(cap_w, "cap_w") > 0, "positive power cap required")
    base = interval(profile["base_w"], "base_w")
    coefficients = {key: interval(value, key) for key, value in profile["dynamic_j_per_event"].items()}
    rows = []
    for index, window in enumerate(windows):
        duration = nonnegative(window["duration_s"], "duration_s")
        require(duration > 0, "positive window duration required")
        unknown = [] if base is not None else ["base_w"]
        unknown.extend(f"missing_count:{name}" for name in profile.get("required_event_keys", [])
                       if name not in window["events"])
        lower, upper = base if base is not None else (0, 0)
        components = {"base": [lower, upper] if base is not None else None}
        for name, count in window["events"].items():
            nonnegative(count, name)
            if count == 0:
                components[name] = [0, 0]
                continue
            coefficient = coefficients.get(name)
            if coefficient is None:
                unknown.append(name)
                components[name] = None
                continue
            part = [coefficient[0] * count / duration, coefficient[1] * count / duration]
            lower += part[0]
            upper += part[1]
            components[name] = part
        status = ("infeasible" if lower > cap_w else "unknown" if unknown else
                  "uncertain" if upper > cap_w else "robust_feasible")
        rows.append({"window": index, "duration_s": duration,
                     "power_w": [lower, None if unknown else upper],
                     "energy_j": [lower * duration, None if unknown else upper * duration],
                     "components_w": components, "unknown_terms": unknown, "status": status})
    statuses = {row["status"] for row in rows}
    status = next(s for s in ("infeasible", "unknown", "uncertain", "robust_feasible") if s in statuses)
    complete = all(row["power_w"][1] is not None for row in rows)
    return {"boundary": boundary, "cap_w": cap_w, "status": status,
            "admitted": status == "robust_feasible", "coefficient_status": profile["status"],
            "peak_window_power_w": [max(r["power_w"][0] for r in rows),
                                    max(r["power_w"][1] for r in rows) if complete else None],
            "energy_j": [sum(r["energy_j"][0] for r in rows),
                         sum(r["energy_j"][1] for r in rows) if complete else None],
            "windows": rows,
            "scope": "piecewise-constant window power; caller must supply a complete system event ledger"}
