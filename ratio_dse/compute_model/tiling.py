"""Array-local dense, grouped, ragged and expert GEMM service estimates."""

from collections import Counter
from fractions import Fraction

from ..area_model.model import broadcast_vectors
from ..common import ANALYTICAL, ceil_div, integer, number, ratio, require
from ..formats import vector_bytes


def _buckets(runs, block):
    """Aggregate repeated logical lengths by the number of issued blocks."""
    for first, last, repeats in runs:
        first = max(1, first)
        while first <= last:
            blocks = ceil_div(first, block)
            end = min(last, blocks * block)
            count = (end - first + 1) * repeats
            yield blocks, count, (first + end) * count // 2
            first = end + 1


def tile_geometry(shape, m_array, n_array, native_k):
    """Count output contexts and full native requests without materializing tiles."""
    m_tile = integer("m_array", m_array)
    n_tile = integer("n_array", n_array)
    k_tile = integer("native_k", native_k)
    tiles = Counter()
    outputs = 0
    full_k = 0
    active_k = 0
    kind = shape["kind"]

    def add(m, n, k, repetitions):
        nonlocal outputs, full_k, active_k
        if repetitions == 0 or not m or not n or not k:
            return
        k_steps = ceil_div(k, k_tile)
        tiles[k_steps] += ceil_div(m, m_tile) * ceil_div(n, n_tile) * repetitions
        cells = m * n * repetitions
        outputs += cells
        full_k += cells * k_steps * k_tile
        active_k += cells * k

    if kind == "experts":
        for m, count in Counter(shape["tokens_per_expert"]).items():
            add(m, shape["n"], shape["k"], count)
    elif kind != "ragged":
        add(shape["m"], shape["n"], shape["k"], shape.get("repetitions", 1))
    else:
        m, fixed = shape["m"], shape["fixed_dimension"]
        m_blocks = ceil_div(m, m_tile)
        qk = shape["axis"] == "n"
        trace = shape.get("key_rows")
        if trace is not None and shape["layout"] == "indexed":
            block = n_tile if qk else k_tile
            for row in trace:
                keys, count = row["key_indices"], row["repetitions"]
                blocks = len({key // block for key in keys})
                if not blocks:
                    continue
                valid = len(keys)
                if qk:
                    k_steps = ceil_div(fixed, k_tile)
                    tiles[k_steps] += m_blocks * blocks * count
                    outputs += m * valid * count
                    full_k += m * valid * count * k_steps * k_tile
                else:
                    tiles[blocks] += m_blocks * ceil_div(fixed, n_tile) * count
                    outputs += m * fixed * count
                    full_k += m * fixed * count * blocks * k_tile
                active_k += m * fixed * valid * count
        else:
            if "execution_length_runs" in shape:
                runs = shape["execution_length_runs"]
            elif trace is not None:
                runs = [[len(row["key_indices"]), len(row["key_indices"]), row["repetitions"]] for row in trace]
            else:
                runs = shape["length_runs"]
            for blocks, count, length_total in _buckets(runs, n_tile if qk else k_tile):
                if qk:
                    k_steps = ceil_div(fixed, k_tile)
                    tiles[k_steps] += m_blocks * blocks * count
                    outputs += m * length_total
                    full_k += m * length_total * k_steps * k_tile
                else:
                    tiles[blocks] += m_blocks * ceil_div(fixed, n_tile) * count
                    outputs += m * fixed * count
                    full_k += m * fixed * count * blocks * k_tile
                active_k += m * fixed * length_total
    requests = sum(steps * count for steps, count in tiles.items())
    return {"tiles_by_k_steps": dict(sorted(tiles.items())), "issue_requests": requests,
            "issued_macs": requests * m_tile * n_tile * k_tile,
            "logical_execution_macs": active_k, "logical_output_elements": outputs,
            "k_tail_utilization": ratio(active_k, full_k)}


def service_cycles(tiles, ii, latency, feedback, contexts):
    """Round-robin waves of equal-K output contexts, draining each wave."""
    integer("II", ii)
    integer("latency", latency)
    integer("context_slots", contexts)
    if feedback is not None:
        integer("feedback_cycles", feedback, latency)
    issue, raw, drain, largest = 0, 0, 0, 0
    for steps, count in tiles.items():
        if steps > 1 and feedback is None:
            return None
        waves, tail = divmod(count, contexts)
        for active, repeat in ((contexts, waves), (tail, int(bool(tail)))):
            if not repeat:
                continue
            largest = max(largest, active)
            issue += (steps * active - 1) * ii * repeat
            raw += (steps - 1) * max(0, (feedback or 0) - active * ii) * repeat
            drain += max(latency, ii) * repeat
    return {"issue_intervals_cycles": issue, "raw_wait_cycles": raw, "drain_cycles": drain,
            "array_service_cycles": issue + raw + drain, "max_active_contexts": largest}


def _local_io(model, geometry, mode, service, shape, broadcast):
    av, bv = broadcast_vectors(shape, broadcast)
    payload, scales = vector_bytes(mode["native_k"], mode["input_layout"])
    requests = geometry["issue_requests"]
    initial_c = model.get("initial_c", "zero")
    require(initial_c in {"zero", "load"}, "initial_c must be zero or load")
    output_bytes = geometry["logical_output_elements"] * 4
    context_bytes = shape[0] * shape[1] * 4 * service["max_active_contexts"] if service is not None else None
    issue_bytes = (av + bv) * (payload + scales) if requests else 0
    return {"a_payload_bytes": requests * av * payload, "b_payload_bytes": requests * bv * payload,
            "scale_metadata_bytes": requests * (av + bv) * scales,
            "initial_c_read_bytes": output_bytes if initial_c == "load" else 0, "final_d_write_bytes": output_bytes,
            "buffer_required_bytes": issue_bytes + context_bytes if context_bytes is not None else None}


def _transfer_cycles(model, io, frequency):
    required = io["buffer_required_bytes"]
    capacity = model.get("buffer_bytes")
    if capacity is None or required is None:
        return None, "buffer_or_feedback_unknown"
    if integer("buffer_bytes", capacity) < required:
        return None, "buffer_capacity_exceeded"
    ingress, egress = model.get("read_bytes_s"), model.get("write_bytes_s")
    if ingress is None or egress is None:
        return None, "interface_bandwidth_unknown"
    rates = [number("interface bandwidth", value) for value in (ingress, egress)]
    require(all(value > 0 for value in rates), "interface bandwidth must be positive")
    read = sum(io[key] for key in ("a_payload_bytes", "b_payload_bytes", "scale_metadata_bytes", "initial_c_read_bytes"))
    return (ceil_div_fraction(read * frequency, ingress)
            + ceil_div_fraction(io["final_d_write_bytes"] * frequency, egress)), None


def ceil_div_fraction(numerator, denominator):
    fraction = numerator / Fraction(str(denominator))
    return ceil_div(fraction.numerator, fraction.denominator)


def evaluate_operator(op, mapping, deployment, profile, array_model):
    """Evaluate one ledger row on one array from A's deployment."""
    fmt, useful = mapping["dp_mode"], op["useful_macs"]
    mode = profile["modes"].get(fmt)
    result = {"op_id": op["op_id"], "deployment_id": deployment["deployment_id"],
              "dp_mode": fmt, "useful_macs": useful, "calibration_status": ANALYTICAL,
              "array_service_time_s": None, "gemm_compute_latency_s": None,
              "ideal_compute_lower_bound_s": None, "issued_macs": None}
    if mode is None:
        known_unsupported = fmt is not None or mapping["multiply_a_format"] == "fp32"
        return result | {"status": "unsupported" if known_unsupported else "unresolved",
                         "reasons": ["unsupported_dp_mode" if known_unsupported else "unresolved_execution_path"]}
    require(deployment["profile_id"] == profile["profile_id"] and deployment["valid"],
            "operator evaluation requires a valid matching deployment")
    require(deployment["frequency_hz"] == profile["frequency_hz"], "deployment clock does not match profile")
    require(array_model["dataflow"] == "serial_output_stationary", "unsupported array dataflow")
    shape = deployment["m_array"], deployment["n_array"]
    k, ii, latency = (mode[key] for key in ("native_k", "ii_cycles", "latency_cycles"))
    clock = integer("frequency_hz", deployment["frequency_hz"])
    geometry = tile_geometry(op["shape"], *shape, k)
    issued = geometry["issued_macs"]
    require(useful <= geometry["logical_execution_macs"] <= issued, "issued geometry does not cover useful MAC")
    feedback = array_model.get("feedback_cycles")
    contexts = array_model["context_slots"]
    service = service_cycles(geometry["tiles_by_k_steps"], ii, latency, feedback, contexts)
    io = _local_io(array_model, geometry, mode, service, shape, deployment["broadcast_model"])
    transfer, reason = _transfer_cycles(array_model, io, clock) if issued else (0, None)
    conversion = mapping["conversion"]
    conversion_cycles = conversion["cycles_per_operator"] if issued else 0
    reasons = []
    if service is None:
        reasons.append("feedback_cycles_unknown")
    if reason:
        reasons.append(reason)
    if conversion_cycles is None:
        reasons.append("conversion_cost_unknown")
    if op["shape"]["kind"] == "ragged" and issued:
        # Local ingress starts after key gathering; expose that external dependency.
        reasons.append("key_gather_outside_array_boundary")
    cycles = service["array_service_cycles"] if service is not None else None
    complete = (cycles + transfer + conversion_cycles
                if cycles is not None and transfer is not None and conversion_cycles is not None else None)
    peak = shape[0] * shape[1] * k / ii
    return result | geometry | (service or {}) | {
        "status": "analytical" if complete is not None else "partial",
        "reasons": reasons, "native_k": k, "ii_cycles": ii, "latency_cycles": latency,
        "ideal_compute_lower_bound_s": useful / peak / clock,
        "array_service_time_s": cycles / clock if cycles is not None else None,
        "shape_utilization": ratio(useful, issued),
        "temporal_utilization": ratio(geometry["issue_requests"] * ii, cycles) if cycles is not None else None,
        "effective_utilization": ratio(useful, peak * cycles) if cycles is not None else None,
        "padding_or_masked_macs": issued - geometry["logical_execution_macs"],
        "redundant_logical_macs": geometry["logical_execution_macs"] - useful,
        "local_transfer_cycles": transfer, "conversion_cycles": conversion_cycles,
        "conversion_bytes": conversion["bytes_per_operator"], "bytes_by_interface": io,
        "gemm_compute_latency_s": complete / clock if complete is not None else None,
        "dataflow": array_model["dataflow"], "context_slots": contexts, "feedback_cycles": feedback,
        "completion_boundary": "one_array_local_ingress_to_local_output",
    }


def evaluate_workload(workload, plan, deployment, profile, array_model):
    """Evaluate each op independently; callers schedule the tile services across arrays."""
    require(plan["workload_id"] == workload["workload_id"], "plan does not match workload")
    require(deployment["profile_id"] == profile["profile_id"] and deployment["valid"],
            "workload evaluation requires a valid matching deployment")
    require(array_model["dataflow"] == "serial_output_stationary", "unsupported array dataflow")
    integer("context_slots", array_model["context_slots"])
    return [evaluate_operator(op, plan["mappings"][op["op_id"]], deployment, profile, array_model)
            | {"workload_id": workload["workload_id"], "precision_plan_id": plan["plan_id"]}
            for op in workload["operators"]]
