"""DP evidence import and integer deployment under a fixed core pool budget."""

from fractions import Fraction
from pathlib import Path

from ..common import (ANALYTICAL, ROOT, SCHEMA_VERSION, ceil_div, digest, identity, integer, number,
                      read_json, require, versioned)
from ..formats import FORMATS, layout, vector_bytes


def _index(records, key):
    index = {}
    for row in records:
        identifier = key(row)
        require(identifier not in index, f"Duplicate evidence for {identifier}")
        index[identifier] = row
    return index


def import_profiles(lock, root=ROOT):
    """Return versioned HardwareProfiles plus the locked input paths."""
    versioned(lock, "evidence lock")
    sources = {}
    for name, entries in lock["sources"].items():
        sources[name] = []
        for entry in entries:
            path = Path(root) / entry["path"]
            require(digest(path) == entry["sha256"], f"Evidence SHA-256 mismatch for {path}")
            sources[name].append((entry, read_json(path) if path.suffix == ".json" else None))
    dc = _index(((row, entry) for entry, document in sources["dc"] for row in document["records"]),
                lambda item: item[0]["top"])
    power = _index(((row, entry, document["condition"]["window"])
                    for entry, document in sources["power"] for row in document["results"]),
                   lambda item: (item[0]["top"], item[0]["format"]))
    profiles = []
    for candidate in lock["candidates"]:
        profile_id, top = candidate["profile_id"], candidate["top"]
        evidence = dc.get(top)
        if evidence is None:
            profiles.append({"profile_id": profile_id, "top": top, "area_um2": None, "modes": {},
                             "ratio_label": candidate["ratio_label"], "status": "missing_evidence",
                             "reason": "missing_dc_record"})
            continue
        row, source = evidence
        high = integer("K_FP16", row["parameters"]["K_FP16"])
        capacities = {"t": high // 2, "h": high, "q": integer("q_native", row["q_native"]),
                      "e": integer("e_native", row["e_native"]), "int8": 2 * high}
        ratio_label = ":".join(str(Fraction(capacities[k], high)) for k in ("h", "q", "e"))
        require(ratio_label == candidate["ratio_label"], f"{top} native K disagrees with locked candidate")
        require(row["technology"]["area_unit"] == "um2", f"{top} area unit must be um2")
        result = row["result"]
        area = number("DP area", result["total_area_um2"])
        require(area > 0, f"{top} DP area must be positive")
        timing = result["setup"] == result["hold"] == "PASS"
        electrical = not row["electrical_violations"]
        valid = result["flow_pass"] and result["synthesis_valid"] and timing and electrical
        profile = {
            "profile_id": profile_id, "ratio_label": ratio_label, "top": top,
            "export_id": row["export_id"], "verification_id": row["verification_id"],
            "verification_receipt_sha256": row["verification_receipt_sha256"],
            "dc_run_id": Path(row["run"]).name, "area_um2": area,
            "frequency_hz": integer("DC frequency", int(row["frequency_mhz"] * 1_000_000)),
            "pvt": row["technology"]["pvt"], "technology_id": row["technology"]["technology_id"],
            "status": "valid" if valid else "failed_timing_or_electrical",
            "timing_pass": timing, "electrical_pass": electrical, "clock_gating": row["clock_gating"],
            "included_components": ["dp"], "evidence": [source, *[entry for entry, _ in sources["spec"]]],
            "artifact_availability": {"dc_summary": (Path(root) / row["run"] / "summary.json").is_file()},
            "modes": {},
        }
        latency = integer("latency_cycles", candidate["latency_cycles"])
        ii = integer("ii_cycles", candidate["ii_cycles"])
        for format_id, (capacity, *_unused) in FORMATS.items():
            k = capacities[capacity]
            mode = {
                "format_id": format_id, "native_k": k, "latency_cycles": latency, "ii_cycles": ii,
                "macs_per_cycle": k / ii, "input_layout": layout(format_id),
                "accumulator_format": "int32" if format_id == "int8" else "fp32",
                "power_status": "missing_evidence", "power_reason": "format_not_measured",
                "power_dynamic_w": None, "power_leakage_w": None, "power_total_w": None,
            }
            point = power.get((top, format_id))
            if point is not None:
                measurement, power_source, window = point
                compatible = (
                    measurement["status"] == measurement["saif_audit"]["status"] == "PASS"
                    and measurement["dc_run"] == row["run"] and measurement["export_id"] == row["export_id"]
                    and measurement["technology"]["technology_id"] == profile["technology_id"]
                    and measurement["technology"]["pvt"] == profile["pvt"]
                    and measurement["frequency_hz"] == profile["frequency_hz"]
                    and measurement["area_um2"] == area and measurement["logical_k"] == k
                )
                mode["power_evidence"] = power_source
                mode["power_run_id"] = Path(measurement["campaign"]).name
                if compatible:
                    mode.update(power_status="measured", power_reason=None, activity_source=window["name"],
                                activity_window_ns=measurement["duration_ns"],
                                power_dynamic_w=number("dynamic_mw", measurement["dynamic_mw"]) / 1000,
                                power_leakage_w=number("static_mw", measurement["static_mw"]) / 1000,
                                power_total_w=number("total_mw", measurement["total_mw"]) / 1000,
                                power_artifact_available=(Path(root) / measurement["audit_path"]).is_file())
                else:
                    mode.update(power_status="incompatible_evidence", power_reason="power_dc_evidence_mismatch")
            profile["modes"][format_id] = mode
        profiles.append(profile)
    return {"schema_version": SCHEMA_VERSION, "profiles": profiles}, [
        Path(root) / entry["path"] for entries in lock["sources"].values() for entry in entries
    ]


def _shape(value):
    require(isinstance(value, (list, tuple)) and len(value) == 2, "shape must be [m_array, n_array]")
    return tuple(integer("shape dimension", dim) for dim in value)


def broadcast_vectors(shape, broadcast):
    """Unique A row and B column vector reads per array tile."""
    m, n = _shape(shape)
    gm, gn = _shape(broadcast["group_shape"])
    shares_a = broadcast["share_a_across_column_groups"]
    shares_b = broadcast["share_b_across_row_groups"]
    require(type(shares_a) is bool and type(shares_b) is bool, "broadcast sharing flags must be boolean")
    return m * (1 if shares_a else ceil_div(n, gn)), n * (1 if shares_b else ceil_div(m, gm))


def _input_rates(mode, shape, broadcast, arrays, frequency):
    a_vectors, b_vectors = broadcast_vectors(shape, broadcast)
    k = integer("native_k", mode["native_k"])
    ii = integer("ii_cycles", mode["ii_cycles"])
    integer("latency_cycles", mode["latency_cycles"])
    payload, metadata = vector_bytes(k, mode["input_layout"])
    a_reuse = integer("a_temporal_reuse", broadcast["a_temporal_reuse"])
    b_reuse = integer("b_temporal_reuse", broadcast["b_temporal_reuse"])
    dispatch = Fraction(arrays * frequency, ii)
    a = dispatch * a_vectors * (payload + metadata) / a_reuse
    b = dispatch * b_vectors * (payload + metadata) / b_reuse
    return a, b, a_vectors, b_vectors, payload + metadata, dispatch


def _mode_demand(mode, shape, broadcast, arrays, frequency, budget):
    a, b, a_vectors, b_vectors, vector_size, dispatch = _input_rates(mode, shape, broadcast, arrays, frequency)
    return {
        "a_vectors_per_array_issue": a_vectors, "b_vectors_per_array_issue": b_vectors,
        "a_input_bytes_s": float(a), "b_input_bytes_s": float(b), "input_bytes_s": float(a + b),
        "input_budget_headroom_bytes_s": float(budget - a - b) if budget is not None else None,
        "saturation_feasible": a + b <= budget if budget is not None else None,
        "ab_one_issue_working_set_bytes_per_core": arrays * (a_vectors + b_vectors) * vector_size,
        "dp_d_stream_bytes_s_per_core": float(dispatch * shape[0] * shape[1] * 4),
    }


def enumerate_deployments(hardware, scenario):
    """Enumerate every requested profile/shape, including infeasible combinations."""
    versioned(hardware, "hardware profiles")
    versioned(scenario, "area scenario")
    profiles = _index(hardware["profiles"], lambda profile: profile["profile_id"])
    scenario_id = scenario["scenario_id"]
    constraint = scenario["constraint_kind"]
    require(constraint in {"equal_array", "equal_input_bandwidth"}, "unsupported constraint_kind")
    baseline = profiles[scenario["baseline_profile"]]
    require(baseline["status"] == "valid", "baseline needs valid DP area and timing evidence")
    require(baseline["included_components"] == ["dp"], "baseline profile must describe a single DP")
    require(scenario["peripheral_policy"] == "fixed_baseline", "unsupported peripheral_policy")
    shape0 = _shape(scenario["baseline_shape"])
    shapes = [_shape(shape) for shape in scenario["legal_shapes"]]
    require(len(set(shapes)) == len(shapes) and shape0 in shapes, "legal_shapes must be unique and include baseline")
    require(constraint != "equal_array" or shapes == [shape0], "equal_array requires only baseline_shape")
    arrays = integer("arrays_per_core", scenario["arrays_per_core"])
    cores0 = integer("baseline_cores", scenario["baseline_cores"])
    alpha = Fraction(str(number("baseline_tensor_fraction", scenario["baseline_tensor_fraction"])))
    require(0 < alpha <= 1, "baseline_tensor_fraction must be in (0, 1]")
    clock = integer("frequency_hz", scenario["frequency_hz"])
    require(clock == baseline["frequency_hz"], "scenario clock must match baseline DP evidence")
    modes = scenario["supported_format_set"]
    require(isinstance(modes, list) and modes and len(set(modes)) == len(modes),
            "supported_format_set must be a nonempty list of unique format IDs")
    require(set(modes) <= baseline["modes"].keys(), "baseline lacks a requested mode")
    broadcast = scenario["broadcast_model"]
    broadcast_vectors(shape0, broadcast)
    extra_area = Fraction(str(number("array_extra_area_um2", scenario.get("array_extra_area_um2", 0))))
    base_area = number("baseline DP area", baseline["area_um2"])
    require(base_area > 0, "baseline DP area must be positive")
    tensor0 = arrays * (shape0[0] * shape0[1] * Fraction(str(base_area)) + extra_area)
    peripheral = tensor0 * (1 / alpha - 1)
    area_budget = cores0 * tensor0 / alpha
    raw_budget = scenario.get("input_budget_bytes_s")
    budget = None
    if raw_budget == "derive_from_baseline":
        demands = [_input_rates(baseline["modes"][fmt], shape0, broadcast, arrays, clock)
                   for fmt in modes]
        budget = max(a + b for a, b, *_ in demands)
    elif raw_budget is not None:
        budget = Fraction(str(number("input_budget_bytes_s", raw_budget)))
    require(constraint != "equal_input_bandwidth" or budget is not None,
            "equal_input_bandwidth requires an explicit or baseline-derived budget")
    output = []
    for profile in profiles.values():
        capability = {fmt: {key: mode[key] for key in ("native_k", "ii_cycles", "latency_cycles", "input_layout")}
                      for fmt, mode in profile["modes"].items()}
        physical = {key: profile.get(key) for key in ("profile_id", "top", "export_id", "dc_run_id",
                                                        "area_um2", "technology_id", "pvt", "status")}
        for shape in shapes:
            m, n = shape
            dp_per_core = m * n * arrays
            area = profile["area_um2"]
            tensor = None
            core = None
            core_count = None
            reasons = []
            if area is not None:
                require(profile["included_components"] == ["dp"], "profiles must describe a single DP")
                area = number("DP area", area)
                require(area > 0, "DP area must be positive")
                tensor = dp_per_core * Fraction(str(area)) + arrays * extra_area
                core = peripheral + tensor
                core_count = int(area_budget // core)
                if not core_count:
                    reasons.append("area_budget_cannot_fit_one_core")
            if profile["status"] != "valid":
                reasons.append(profile["status"])
            same_condition = (profile.get("frequency_hz") == clock
                              and profile.get("technology_id") == baseline.get("technology_id")
                              and profile.get("pvt") == baseline.get("pvt")
                              and profile.get("clock_gating") == baseline.get("clock_gating"))
            if area is not None and not same_condition:
                reasons.append("incompatible_dp_condition")
            by_mode = {}
            for fmt in sorted(set(modes) | profile["modes"].keys()):
                mode = profile["modes"].get(fmt)
                if mode is None:
                    by_mode[fmt] = {"status": "missing_evidence" if area is None else "unsupported"}
                    if fmt in modes:
                        reasons.append(f"unavailable_required_mode:{fmt}")
                    continue
                metrics = _mode_demand(mode, shape, broadcast, arrays, clock, budget)
                if fmt in modes and metrics["saturation_feasible"] is False and constraint == "equal_input_bandwidth":
                    reasons.append(f"input_budget_exceeded:{fmt}")
                core_peak = float(Fraction(dp_per_core * clock * mode["native_k"], mode["ii_cycles"]))
                peak_valid = same_condition and profile["status"] == "valid"
                by_mode[fmt] = {**metrics, "status": "supported", "native_k": mode["native_k"],
                                "core_peak_macs_s": core_peak if peak_valid else None,
                                "pool_peak_macs_s": core_peak * core_count if peak_valid and core_count is not None else None}
            output.append({
                "deployment_id": identity("deployment", [scenario, physical, capability, [m, n]]),
                "scenario_id": scenario_id, "constraint_kind": constraint, "profile_id": profile["profile_id"],
                "ratio_label": profile["ratio_label"], "m_array": m, "n_array": n, "arrays_per_core": arrays,
                "dp_per_core": dp_per_core, "core_count": core_count, "frequency_hz": clock,
                "area_tensor_um2_per_core": float(tensor) if tensor is not None else None,
                "area_peripheral_um2_per_core": float(peripheral),
                "area_core_um2": float(core) if core is not None else None,
                "area_pool_um2": float(core * core_count) if core is not None else None,
                "area_pool_mm2": float(core * core_count / 1_000_000) if core is not None else None,
                "area_budget_um2": float(area_budget), "area_budget_mm2": float(area_budget / 1_000_000),
                "unused_area_um2": float(area_budget - core * core_count) if core is not None else None,
                "input_budget_bytes_s": float(budget) if budget is not None else None,
                "per_mode_peak_macs_s": {fmt: values.get("pool_peak_macs_s") for fmt, values in by_mode.items()},
                "modes": by_mode, "broadcast_model": broadcast, "valid": not reasons, "reasons": reasons,
                "calibration_status": ANALYTICAL,
                "excluded_components": ["HBM", "package", "uncharacterized_array_overhead"],
            })
    base = next(row for row in output if row["profile_id"] == baseline["profile_id"]
                and (row["m_array"], row["n_array"]) == shape0)
    require(base["core_count"] == cores0, "baseline core count failed to round-trip")
    return {"schema_version": SCHEMA_VERSION, "scenario": scenario, "deployments": output,
            "baseline_deployment_id": base["deployment_id"], "baseline_core_count": cores0}
