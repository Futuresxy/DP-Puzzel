"""Analytical GEMM scheduling with a local-memory and DP power boundary."""

from collections import Counter
from functools import lru_cache
from math import ceil, floor

from ..area_model.model import broadcast_vectors
from ..common import ratio, require
from ..compute_model.tiling import service_cycles, tile_geometry
from ..formats import vector_bytes


def partition_tiles(tiles, arrays):
    """Stripe independent output tiles across arrays, keeping each tile's K chain intact."""
    lanes = [Counter() for _ in range(arrays)]
    cursor = 0
    for steps, count in sorted(tiles, reverse=True):
        whole, tail = divmod(count, arrays)
        if whole:
            for lane in lanes:
                lane[steps] = whole
        for offset in range(tail):
            lanes[(cursor + offset) % arrays][steps] += 1
        cursor = (cursor + tail) % arrays
    return lanes


@lru_cache(maxsize=65536)
def _array_work(tiles, ii, latency, feedback, contexts):
    service = service_cycles(dict(tiles), ii, latency, feedback, contexts)
    return (service["array_service_cycles"], sum(k * count for k, count in tiles),
            sum(count for _, count in tiles), service["max_active_contexts"])


@lru_cache(maxsize=32768)
def _lane_classes(tiles, available_arrays, cores, ii, latency, feedback, contexts):
    active = min(available_arrays, sum(count for _, count in tiles))
    if not active:
        return (), 0
    array_occupancy = Counter(lane % cores for lane in range(active))
    classes = set()
    for lane_id, lane in enumerate(partition_tiles(tiles, active)):
        # Arrays on a core reserve equal shares of its two local ports.
        work = _array_work(tuple(sorted(lane.items())), ii, latency, feedback, contexts)
        classes.add((*work, array_occupancy[lane_id % cores]))
    return tuple(sorted(classes)), active


@lru_cache(maxsize=32768)
def group_service(tiles, available_arrays, cores, ii, latency, feedback, contexts,
                  issue_bytes, output_bytes, read_bytes_per_cycle, write_bytes_per_cycle):
    classes, active = _lane_classes(tiles, available_arrays, cores, ii, latency, feedback, contexts)
    critical = (0, 0, 0, 0, 0)
    for compute, requests, outputs, active_contexts, slots in classes:
        read = ceil(requests * issue_bytes * slots / read_bytes_per_cycle) if issue_bytes else 0
        write = ceil(outputs * output_bytes * slots / write_bytes_per_cycle) if output_bytes else 0
        critical = max(critical, (compute + read + write, compute, read, write, active_contexts))
    return critical, active, max((row[3] for row in classes), default=0)


@lru_cache(maxsize=65536)
def buffered_lane_service(tiles, ii, latency, feedback, contexts, issue_bytes,
                          output_bytes, read_bytes_per_cycle, write_bytes_per_cycle, banks):
    """K-round buffers; independent refill/issue ports, serial wave writeback.

    One bank holds A/B (including scales) for all contexts in one K round.
    A consumed bank is reusable after that round's last issue interval. For
    two banks the exact equal-round recurrence reduces to max(refill, RAW,
    issue duration). Waves drain/write before the next wave's first refill.
    No cross-request operand reuse or cross-wave prefetch is assumed.
    """
    require(banks in (1, 2), "input banks must be one or two")
    total = compute = read = write = largest = 0
    for steps, count in tiles:
        waves, tail = divmod(count, contexts)
        for active, repeat in ((contexts, waves), (tail, int(bool(tail)))):
            if not repeat:
                continue
            refill = ceil(active * issue_bytes / read_bytes_per_cycle)
            issue = active * ii
            stride = max(refill, issue, feedback) if banks == 2 else max(refill + issue, feedback)
            drain = (active - 1) * ii + max(latency, ii)
            store = ceil(active * output_bytes / write_bytes_per_cycle)
            duration = refill + (steps - 1) * stride + drain + store
            service = (steps - 1) * max(issue, feedback) + drain
            total += repeat * duration
            compute += repeat * service
            read += repeat * steps * refill
            write += repeat * store
            largest = max(largest, active)
    return (total, compute, read, write, largest)


@lru_cache(maxsize=32768)
def buffered_group_service(tiles, available_arrays, cores, ii, latency, feedback, contexts,
                           issue_bytes, output_bytes, read_bytes_per_cycle, write_bytes_per_cycle, banks):
    active = min(available_arrays, sum(count for _, count in tiles))
    if not active:
        return (0, 0, 0, 0, 0), 0, 0
    occupancy = Counter(lane % cores for lane in range(active))
    classes = {(tuple(sorted(lane.items())), occupancy[index % cores])
               for index, lane in enumerate(partition_tiles(tiles, active))}
    costs = [buffered_lane_service(lane, ii, latency, feedback, contexts, issue_bytes, output_bytes,
                                  read_bytes_per_cycle / slots, write_bytes_per_cycle / slots, banks)
             for lane, slots in classes]
    return max(costs), active, max(row[4] for row in costs)


def tile_groups(shape, m, n, native_k, policy):
    """Return separate launch groups with multiplicities and the pooled B geometry."""
    geometry = tile_geometry(shape, m, n, native_k)
    groups = [(1, tuple(geometry["tiles_by_k_steps"].items()))]
    if policy == "isolated_weights" and shape["kind"] == "experts":
        groups = [
            (count, tuple(tile_geometry({"kind": "dense", "m": tokens, "n": shape["n"], "k": shape["k"]},
                                        m, n, native_k)["tiles_by_k_steps"].items()))
            for tokens, count in sorted(Counter(shape["tokens_per_expert"]).items()) if tokens
        ]
    elif policy == "isolated_weights" and shape["kind"] == "grouped":
        individual = tile_geometry(shape | {"repetitions": 1}, m, n, native_k)
        groups = [(shape.get("repetitions", 1), tuple(individual["tiles_by_k_steps"].items()))]
    return geometry, groups


def power_terms(dp_count, dp_per_array, mode, idle_fraction, activity_scale=1.0):
    """Installed leakage plus an explicit issue/idle dynamic proxy."""
    dynamic = mode["power_dynamic_w"] * activity_scale
    idle_w = dp_count * (mode["power_leakage_w"] + idle_fraction * dynamic)
    active_increment_w = dp_per_array * dynamic * (1 - idle_fraction)
    return idle_w, active_increment_w


def array_limit(arrays, cap_w, idle_w, increment_w):
    if cap_w is None:
        return arrays
    if cap_w < idle_w:
        return 0
    return min(arrays, max(0, floor((cap_w - idle_w) / increment_w))) if increment_w else arrays


def operator_cost(op, geometry, groups, deployment, mode, settings):
    m, n, cores = (deployment[key] for key in ("m_array", "n_array", "core_count"))
    arrays = deployment["arrays_per_core"] * cores
    dp_per_array = m * n
    freq = deployment["frequency_hz"]
    ii, latency = mode["ii_cycles"], mode["latency_cycles"]
    idle, increment = power_terms(arrays * dp_per_array, dp_per_array, mode, settings["idle_fraction"],
                                  settings.get("activity_scale", 1.0))
    cap = settings["cap_w"]
    power_granularity = settings.get("power_granularity", "array")
    require(power_granularity in ("array", "core"), "power_granularity must be array or core")
    if power_granularity == "core":
        scheduling_cores = array_limit(cores, cap, idle, deployment["arrays_per_core"] * increment)
        allowed = scheduling_cores * deployment["arrays_per_core"]
    else:
        allowed = array_limit(arrays, cap, idle, increment)
        scheduling_cores = cores
    requests = geometry["issue_requests"]
    if requests and not allowed:
        return None
    vectors = broadcast_vectors((m, n), deployment["broadcast_model"])
    ab = sum(vectors) * sum(vector_bytes(mode["native_k"], mode["input_layout"]))
    d = 4 * dp_per_array
    issue_bytes = ab if settings["include_local"] else 0
    output_bytes = d if settings["include_local"] else 0
    bw = settings["local_tb_s"] * 1e12 / freq
    schedule = settings.get("io_schedule", "serial")
    require(schedule in ("serial", "single_buffer", "pingpong"), "unknown io_schedule")
    contexts = settings["contexts"]
    banks = 2 if schedule == "pingpong" else 1
    if schedule != "serial":
        require(settings.get("operand_delivery") == "native_issue_width",
                "buffered schedule requires an explicit native_issue_width operand port")
        contexts = min(contexts, settings["buffer_bytes_per_array"] // (banks * ab + d))
        if not contexts:
            return None
    cycles = compute = read = write = 0
    concurrency = 0
    required_buffer = 0
    for count, tiles in groups:
        if not tiles:
            continue
        args = (tiles, allowed, scheduling_cores, ii, latency, latency, contexts,
                issue_bytes, output_bytes, bw, bw * settings["write_read_ratio"])
        critical, active, largest_context_count = (group_service(*args) if schedule == "serial" else
                                                   buffered_group_service(*args, banks))
        buffer = (ab + d * largest_context_count if schedule == "serial" else
                  (banks * ab + d) * largest_context_count)
        required_buffer = max(buffer, required_buffer)
        if buffer > settings["buffer_bytes_per_array"]:
            return None
        duration, c, a, b, _ = critical
        cycles += count * duration
        compute += count * c
        read += count * a
        write += count * b
        concurrency = max(active, concurrency)
    seconds = cycles / freq
    energy = idle * seconds + increment * requests * ii / freq if requests else 0.0
    tile_count = sum(geometry["tiles_by_k_steps"].values())
    payload = requests * ab
    output = tile_count * d
    return {
        "seconds": seconds, "compute_s": compute / freq, "read_s": read / freq, "write_s": write / freq,
        "dp_energy_j": energy, "dp_envelope_w": idle + concurrency * increment if requests else 0.0,
        "dp_full_pool_mode_w": idle + arrays * increment if requests else 0.0,
        "issued_macs": geometry["issued_macs"], "requests": requests, "tiles": tile_count,
        "ab_bytes": payload, "d_bytes": output, "useful_macs": op["useful_macs"],
        "intensity_macs_byte": ratio(op["useful_macs"], payload + output),
        "active_arrays": concurrency, "eligible_arrays": allowed,
        "active_cores": min(scheduling_cores, concurrency),
        "eligible_cores": scheduling_cores if power_granularity == "core" else min(cores, allowed),
        "buffer_required_bytes": required_buffer, "effective_contexts": contexts,
        "overlap_s": (compute + read + write - cycles) / freq,
        "native_k": mode["native_k"], "shape_utilization": ratio(op["useful_macs"], geometry["issued_macs"]),
        "peak_macs_s_per_local_byte_s": deployment["dp_per_core"] * mode["macs_per_cycle"] / bw,
    }


def pareto_indices(rows, fields):
    """Return all nondominated rows, preserving exact ties."""
    points = [tuple(row[field] for field in fields) for row in rows]
    return [i for i, point in enumerate(points)
            if not any(all(x <= y for x, y in zip(other, point)) and other != point for other in points)]
