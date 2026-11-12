"""Analytical GEMM scheduling with a local-memory and DP power boundary."""

from collections import Counter
from functools import lru_cache
from math import ceil, floor

from ..area_model.model import broadcast_vectors
from ..common import ratio
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
    allowed = array_limit(arrays, cap, idle, increment)
    requests = geometry["issue_requests"]
    if requests and not allowed:
        return None
    vectors = broadcast_vectors((m, n), deployment["broadcast_model"])
    ab = sum(vectors) * sum(vector_bytes(mode["native_k"], mode["input_layout"]))
    d = 4 * dp_per_array
    issue_bytes = ab if settings["include_local"] else 0
    output_bytes = d if settings["include_local"] else 0
    bw = settings["local_tb_s"] * 1e12 / freq
    cycles = compute = read = write = 0
    concurrency = 0
    for count, tiles in groups:
        if not tiles:
            continue
        critical, active, largest_context_count = group_service(
            tiles, allowed, cores, ii, latency, latency, settings["contexts"],
            issue_bytes, output_bytes, bw, bw * settings["write_read_ratio"],
        )
        if ab + d * largest_context_count > settings["buffer_bytes_per_array"]:
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
        "native_k": mode["native_k"], "shape_utilization": ratio(op["useful_macs"], geometry["issued_macs"]),
        "peak_macs_s_per_local_byte_s": deployment["dp_per_core"] * mode["macs_per_cycle"] / bw,
    }


def pareto_indices(rows, fields):
    """Return all nondominated rows, preserving exact ties."""
    points = [tuple(row[field] for field in fields) for row in rows]
    return [i for i, point in enumerate(points)
            if not any(all(x <= y for x, y in zip(other, point)) and other != point for other in points)]
