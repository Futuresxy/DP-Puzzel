"""Normalize DeepSeek or external GEMMs without tying their shapes to a DP."""

from graphlib import TopologicalSorter
from pathlib import Path

from paper.scripts import deepseek_v41 as v41

from ..common import ROOT, SCHEMA_VERSION, digest, identity, integer, path_label, read_json, require, versioned

MODEL_ROOT = ROOT / "paper/data/inputs/models"
MODELS = {"DeepSeek-V4-Flash": "v4", "DeepSeek-V4-Pro": "v4", "DeepSeek-V4.1-Flash": "v41"}
VARIANTS = {"reference", "target_native_20261112"}


def floor_runs(past, tokens, divisor, cap=None):
    """[first length, last length, repetitions per length] for floor(t/divisor)."""
    lo, hi = past + 1, past + tokens
    first, last = lo // divisor, hi // divisor
    if cap is not None:
        last = min(last, cap)
        first = min(first, cap)
    if first == last:
        return [[first, first, tokens]]
    runs = [[first, first, (first + 1) * divisor - lo]]
    if last - first > 1:
        runs.append([first + 1, last - 1, divisor])
    runs.append([last, last, hi - last * divisor + 1])
    return runs


def candidate_runs(past, tokens, divisor, blocks, block_size, policy):
    cap = blocks * block_size
    if policy == "upper_bound":
        return floor_runs(past, tokens, divisor, cap)
    require(policy == "pinned_blocks", "unknown candidate_policy")
    result = []
    for first, last, repeats in floor_runs(past, tokens, divisor):
        if first <= cap:
            result.append([first, min(last, cap), repeats])
        first = max(cap + 1, first)
        if first > last:
            continue
        periods, tail = divmod(last - first + 1, block_size)
        if periods:
            result.append([cap - block_size + 1, cap, periods * repeats])
        if tail:
            start = (first - 1) % block_size
            end = min(block_size, start + tail)
            result.append([cap - block_size + start + 1, cap - block_size + end, repeats])
            if start + tail > block_size:
                result.append([cap - block_size + 1, cap - block_size + start + tail - block_size, repeats])
    return result


def _category(kernel):
    if kernel.startswith("index."):
        return "attention_core", "indexer_" + kernel.removeprefix("index.")
    if kernel.startswith(("swa.", "csa.", "hca.")):
        family, operator = kernel.split(".")
        return "attention_core", f"{family}_{operator}"
    if kernel in {"q_down", "q_up", "swa_kv", "window_kv", "o_group", "o_final", "global_kv.projection"}:
        return "attention_projection", kernel
    if kernel.startswith("moe.shared."):
        return "shared_or_dense_ffn", kernel.removeprefix("moe.shared.")
    if kernel.startswith("moe.routed."):
        return "routed_expert", kernel.removeprefix("moe.routed.")
    return "residual_gemm", kernel


def _row(phase, segment, layer, kernel, shape, label, **meta):
    category, subcategory = _category(kernel)
    return {"op_id": f"{phase}/{segment}/{layer}/{kernel}", "stage": phase, "segment": segment,
            "layer_id": layer, "operator": kernel, "category": category, "subcategory": subcategory,
            "shape": shape, "precision_label": label, "dependencies": [], **meta}


def _matrix(m, n, k, repeats=1, *, kind="dense"):
    return {"kind": kind, "m": m, "n": n, "k": k, "repetitions": repeats}


def _ragged(axis, heads, width, runs, batch, **extra):
    return {"kind": "ragged", "axis": axis, "m": heads, "fixed_dimension": width,
            "length_runs": [[first, last, count * batch] for first, last, count in runs],
            "layout": "compact_gather", "source": "analytical_lengths", **extra}


def _expert(config, assignments, n, k, policy):
    experts = config["n_routed_experts"]
    if policy == "balanced":
        q, remainder = divmod(assignments, experts)
        tokens = [q + (i < remainder) for i in range(experts)]
    else:
        require(policy == "hot_experts", "routing_policy must be balanced or hot_experts")
        active = config["n_activated_experts"]
        require(0 < active <= experts and assignments % active == 0, "invalid top-k routing configuration")
        tokens = [assignments // active] * active + [0] * (experts - active)
    return {"kind": "experts", "n": n, "k": k, "tokens_per_expert": tokens, "source": policy,
            "tokens_per_expert_limit": assignments // config["n_activated_experts"]}


def _v41_rows(config_path, options, phase, past, tokens, batch, variant):
    config = v41.load_config(config_path)
    schedule = options["schedule"]
    indexer = "reference" if variant == "reference" else "native"
    policy = options.get("candidate_policy", "pinned_blocks")
    if phase == "decode":
        require(schedule == "decode", "decode requires schedule=decode")
        old = []
        for step in range(tokens):
            rows = v41.decode_work(past + step, 1, batch=batch, config=config, indexer=indexer,
                                    candidate_policy=policy)
            old.extend(row | {"segment": f"{row['segment']}_{step}"} for row in rows)
    elif schedule == "simplified":
        require(past == 0, "simplified prefill requires past_tokens=0")
        old = v41.simplified_prefill_work(tokens, batch=batch, config=config)
        if indexer == "reference":
            # Replay the same scope with the historical rectangular Indexer.
            ref = v41.prefill_work(tokens, batch=batch, config=config, prefill_schedule="ced",
                                   indexer=indexer, candidate_policy=policy, include_mhc=False,
                                   include_engram=False, include_head=False)
            kept = {(row["layer_id"], row["segment"]) for row in old}
            old = [row for row in ref if (row["layer_id"], row["segment"]) in kept]
        elif policy != "pinned_blocks":
            raise ValueError("simplified native prefill uses candidate_policy=pinned_blocks")
    else:
        require(past == 0 and schedule in {"ced", "full"}, "V4.1 ced/full prefill requires past_tokens=0")
        old = v41.prefill_work(tokens, batch=batch, config=config, prefill_schedule=schedule,
                               indexer=indexer, candidate_policy=policy)
    owners = {row["layer_id"]: row for row in v41.layer_schedule(config)}
    output = []
    for row in old:
        phase, segment, layer, kernel = row["phase"], row["segment"], row["layer_id"], row["kernel"]
        kernel = kernel.replace("global.qk", "csa.qk").replace("global.pv", "csa.pv")
        p, t = row["past_tokens"], row["query_tokens"]
        r = row.get("ratio")
        meta = {"source_basis": row["formula"], "historical_macs": row["flops"] // 2}
        if layer >= 0:
            owner = owners[layer]
            meta.update(kv_owner_layer=owner["kv_owner"], index_owner_layer=owner["index_owner"],
                        compression_ratio=r, past_tokens=p, query_tokens=t)
        if kernel.startswith(("swa.", "csa.")):
            axis = "n" if kernel.endswith(".qk") else "k"
            runs = (floor_runs(row["local_past"], t, 1, config.window_size) if kernel.startswith("swa.")
                    else floor_runs(p, t, r, config.index_topk))
            shape = _ragged(axis, config.n_heads, config.head_dim, runs, batch)
        elif kernel in {"index.full_qk", "index.candidate_qk"}:
            runs = (floor_runs(p, t, r) if kernel == "index.full_qk"
                    else candidate_runs(p, t, r, config.candidate_topk_blocks, config.candidate_block_size, policy))
            shape = _ragged("n", config.index_n_heads, config.index_head_dim, runs, batch)
            if indexer == "reference":
                execution = [[(p+t)//r, (p+t)//r, t*batch]] if phase == "prefill" else [
                    [lo, hi, count * batch] for lo, hi, count in floor_runs(p, t, r)]
                shape["execution_length_runs"] = execution
        elif row["shape_kind"] == "expert_assignments":
            if kernel.startswith("moe.routed."):
                shape = _expert(vars(config), row["m"], row["n"], row["k"], options["routing_policy"])
            else:
                shape = _matrix(row["m"] // config.n_shared_experts, row["n"], row["k"],
                                config.n_shared_experts, kind="grouped")
        else:
            kind = "grouped" if row["repeat"] > 1 else "dense"
            shape = _matrix(row["m"], row["n"], row["k"], row["repeat"], kind=kind)
        if shape.get("m") == 0 or shape.get("repetitions") == 0:
            continue
        label = row["precision"]
        if kernel.startswith("moe.routed."):
            label = "W4A8"
        if variant != "reference" and kernel == "global_kv.projection":
            label = "BF16"
        output.append(_row(phase, segment, layer, kernel, shape, label, **meta))
    return output


def _v4_rows(config, options, phase, past, tokens, batch, variant):
    require(options["schedule"] == ("full" if phase == "prefill" else "decode"),
            "V4 uses full prefill or one-query decode steps")
    d, h, hd, q = (integer(key, config[key]) for key in ("dim", "n_heads", "head_dim", "q_lora_rank"))
    groups, o, ff = (integer(key, config[key]) for key in ("o_groups", "o_lora_rank", "moe_inter_dim"))
    ih, idim, hc = (integer(key, config[key]) for key in ("index_n_heads", "index_head_dim", "hc_mult"))
    require(h * hd % groups == 0, "V4 projection groups must divide the projection width")
    output = []

    def emit(layer, kernel, shape, label, **meta):
        output.append(_row(phase, segment, layer, kernel, shape, label, **meta))

    def linear(layer, kernel, n, k, label, repeats=1, *, m=None):
        emit(layer, kernel, _matrix(batch * count if m is None else m, n, k, repeats,
                                    kind="grouped" if repeats > 1 else "dense"), label)

    spans = [(past, tokens, "prefill")] if phase == "prefill" else [
        (past + step, 1, f"decode_{step}") for step in range(tokens)]
    ratios = config["compress_ratios"][:config["n_layers"]]
    require(len(ratios) == config["n_layers"] and set(ratios) <= {0, 4, 128},
            "unsupported V4 compression schedule")
    for history, count, segment in spans:
        for layer, r in enumerate(ratios):
            for name, n, k in (("q_down", q, d), ("q_up", h*hd, q),
                               ("window_kv", hd, d), ("o_final", d, groups*o)):
                linear(layer, name, n, k, "FP8")
            linear(layer, "o_group", o, h*hd//groups, "BF16", groups)
            attentions = [("swa", floor_runs(history, count, 1, config["window_size"]))]
            if r:
                attentions.append(("csa" if r == 4 else "hca",
                                   floor_runs(history, count, r, config["index_topk"] if r == 4 else None)))
            for family, runs in attentions:
                for suffix, axis in (("qk", "n"), ("pv", "k")):
                    emit(layer, f"{family}.{suffix}", _ragged(axis, h, hd, runs, batch), "BF16")
            for suffix, n, k in (("gate", ff, d), ("up", ff, d), ("down", d, ff)):
                assignments = batch * count * config["n_activated_experts"]
                label = "W4A8" if config.get("expert_dtype") == "fp4" else "FP8"
                emit(layer, "moe.routed." + suffix, _expert(config, assignments, n, k, options["routing_policy"]),
                     label, weight_storage_hint=config.get("expert_dtype"),
                     source_basis="historical V4 work groups these assignments under FP8")
                linear(layer, "moe.shared." + suffix, n, k, "FP8", config["n_shared_experts"])
            linear(layer, "moe.router", config["n_routed_experts"], d, "FP32")
            for sublayer in ("attention", "ffn"):
                linear(layer, "mhc." + sublayer, hc*(hc+2), hc*d, "FP32")
            if r:
                for suffix in ("kv", "gate"):
                    linear(layer, "compressor." + suffix, hd*(2 if r == 4 else 1), d, "FP32")
            if r == 4:
                linear(layer, "index.q_projection", ih*idim, q, "FP8")
                linear(layer, "index.head_weights", ih, d, "BF16")
                for suffix in ("kv", "gate"):
                    linear(layer, "index.compressor." + suffix, 2*idim, d, "FP32")
                shape = _ragged("n", ih, idim, floor_runs(history, count, r), batch)
                if variant == "reference" and phase == "prefill":
                    entries = (history+count)//r
                    shape["execution_length_runs"] = [[entries, entries, batch*count]]
                emit(layer, "index.full_qk", shape, "BF16" if variant == "reference" else "FP4")
        linear(-1, "hc_head", hc*hc, d, "FP32")
        linear(-1, "lm_head", config["vocab_size"], d, "FP32", m=batch)
    return output


def _stats(runs):
    length_total, row_count = 0, 0
    for first, last, repeats in runs:
        integer("first length", first, 0)
        integer("last length", last, first)
        integer("length repetitions", repeats)
        rows = (last - first + 1) * repeats
        length_total += (first + last) * rows // 2
        row_count += rows
    return length_total, row_count


def _trace_stats(shape):
    require(shape["layout"] in {"compact_gather", "indexed"}, "unsupported ragged layout")
    if "key_rows" in shape:
        runs = []
        for row in shape["key_rows"]:
            indices = row["key_indices"]
            require(isinstance(indices, list) and indices == sorted(set(indices)), "key_indices must be sorted and unique")
            require(all(type(key) is int and key >= 0 for key in indices), "invalid key index")
            runs.append([len(indices), len(indices), row["repetitions"]])
        return _stats(runs)
    require(shape["layout"] == "compact_gather", "indexed layout requires key_rows")
    return _stats(shape["length_runs"])


def work_macs(shape):
    kind = shape["kind"]
    if kind in {"dense", "grouped"}:
        return (integer("m", shape["m"]) * integer("n", shape["n"]) * integer("k", shape["k"])
                * integer("repetitions", shape.get("repetitions", 1)))
    if kind == "experts":
        tokens = shape["tokens_per_expert"]
        limit = shape.get("tokens_per_expert_limit")
        require(isinstance(tokens, list) and tokens, "tokens_per_expert must contain one entry per expert")
        total = sum(integer("expert tokens", t, 0) for t in tokens)
        if limit is not None:
            require(max(tokens) <= integer("tokens_per_expert_limit", limit, 0),
                    "one expert cannot receive more assignments than there are tokens")
        return total * integer("n", shape["n"]) * integer("k", shape["k"])
    require(kind == "ragged" and shape["axis"] in {"n", "k"}, "unsupported shape kind or ragged axis")
    length, rows = _trace_stats(shape)
    if "execution_length_runs" in shape:
        executed, executed_rows = _stats(shape["execution_length_runs"])
        require(rows == executed_rows and length <= executed and shape["layout"] == "compact_gather",
                "ragged execution lengths must cover useful lengths and the same number of rows")
    return length * integer("m", shape["m"]) * integer("fixed_dimension", shape["fixed_dimension"])


def _validate_ops(rows):
    seen = set()
    output = []
    for row in rows:
        key = row["op_id"]
        require(isinstance(key, str) and key and key not in seen, f"duplicate or invalid op_id {key}")
        seen.add(key)
        macs = work_macs(row["shape"])
        require(row.get("useful_macs", macs) == macs, f"{key} useful_macs disagrees with shape")
        output.append(dict(row, useful_macs=macs, useful_flops=2*macs))
    for row in output:
        require(isinstance(row["dependencies"], list), f"dependencies for {row['op_id']} must be a list")
        require(set(row["dependencies"]) <= seen - {row["op_id"]}, f"invalid dependency for {row['op_id']}")
    tuple(TopologicalSorter({row["op_id"]: row["dependencies"] for row in output}).static_order())
    return output


def _with_dependencies(rows):
    """Known GEMM dependencies within a layer/segment and explicit KV ownership."""
    lookup = {(op["segment"], op["layer_id"], op["operator"]): op["op_id"] for op in rows}
    links = {
        "q_up": ("q_down",), "index.q_projection": ("q_down",),
        "index.full_qk": ("index.q_projection", "index.k_projection", "index.compressor.kv"),
        "index.candidate_qk": ("index.q_projection",),
        "swa.qk": ("q_up", "swa_kv", "window_kv"), "swa.pv": ("swa.qk", "swa_kv", "window_kv"),
        "csa.qk": ("q_up", "global_kv.projection", "compressor.kv", "index.full_qk", "index.candidate_qk"),
        "csa.pv": ("csa.qk", "global_kv.projection", "compressor.kv"),
        "hca.qk": ("q_up", "compressor.kv"), "hca.pv": ("hca.qk", "compressor.kv"),
        "index.k_projection": ("global_kv.projection",),
        "o_group": ("swa.pv", "csa.pv", "hca.pv"), "o_final": ("o_group",), "moe.router": ("o_final",),
        "moe.shared.gate": ("o_final",), "moe.shared.up": ("o_final",),
        "moe.shared.down": ("moe.shared.gate", "moe.shared.up"),
        "moe.routed.gate": ("moe.router",), "moe.routed.up": ("moe.router",),
        "moe.routed.down": ("moe.routed.gate", "moe.routed.up"),
    }
    output = []
    for op in rows:
        segment, layer, operator = op["segment"], op["layer_id"], op["operator"]
        keys = [(segment, layer, name) for name in links.get(operator, ())]
        if operator in {"csa.qk", "csa.pv", "index.candidate_qk"}:
            owner = op.get("kv_owner_layer", -1)
            keys += [(segment, owner, "global_kv.projection"),
                     ("decoder_cache_build", owner, "global_kv.projection")]
        if operator == "csa.qk" and 0 <= op.get("index_owner_layer", -1) < layer:
            owner = op["index_owner_layer"]
            keys += [(segment, owner, "index.full_qk"), (segment, owner, "index.candidate_qk")]
        output.append(dict(op, dependencies=sorted({lookup[key] for key in keys if key in lookup})))
    return output


def _trace_group(row):
    operator, kind = row["operator"], row["shape"]["kind"]
    if kind == "experts" or operator.startswith(("swa.", "csa.", "hca.")):
        operator = operator.rsplit(".", 1)[0]
    return row["stage"], row["segment"], row["layer_id"], operator


def _apply_trace(rows, trace):
    versioned(trace, "runtime observations")
    observations = trace["ops"]
    lookup = {row["op_id"]: row for row in rows}
    require(observations.keys() <= lookup.keys(), "runtime observations contain unknown op IDs")
    # Gate/up/down share one routing decision; QK and PV share selected keys.
    overrides = {}
    for key, record in observations.items():
        row = lookup[key]
        kind = row["shape"]["kind"]
        require(kind in {"experts", "ragged"}, f"{key} does not accept sparse or routing observations")
        group = _trace_group(row)
        require(group not in overrides or overrides[group] == record, f"conflicting observations for {group}")
        overrides[group] = record
    output = []
    for row in rows:
        shape, key = row["shape"], row["op_id"]
        group = _trace_group(row)
        if group in overrides:
            record = overrides[group]
            if shape["kind"] == "experts":
                tokens = record["tokens_per_expert"]
                require(len(tokens) == len(shape["tokens_per_expert"]), f"{key} observed expert count changed")
                observed = dict(shape, tokens_per_expert=tokens, source="observed")
                require(work_macs(shape) == work_macs(observed), f"{key} observed total assignments changed")
            else:
                require(shape["kind"] == "ragged", f"{key} does not accept sparse or routing observations")
                observed = dict(shape, key_rows=record["key_rows"], layout=record.get("layout", "compact_gather"),
                                source="observed")
                require(_trace_stats(shape)[1] == _trace_stats(observed)[1], f"{key} observed row count changed")
            row = dict(row, shape=observed)
        output.append(row)
    return output


def build_workload(options, *, config_path=None, trace=None):
    """Build a versioned ledger from a scenario and optional shape observations."""
    versioned(options, "workload scenario")
    model = options["model_id"]
    adapter = options.get("adapter") or MODELS[model]
    require(adapter in {"v4", "v41"}, "unsupported model adapter")
    config_path = Path(config_path) if config_path else MODEL_ROOT / model / "inference/config.json"
    config = read_json(config_path)
    phase, variant = options["stage"], options["variant"]
    require(phase in {"prefill", "decode"} and variant in VARIANTS, "unsupported stage or variant")
    tokens, past = integer("query_tokens", options["query_tokens"]), integer("past_tokens", options["past_tokens"], 0)
    batch = integer("batch", options["batch"])
    require(options["routing_policy"] in {"balanced", "hot_experts"}, "invalid routing_policy")
    if adapter == "v41":
        require(past + tokens <= v41.load_config(config_path).max_context, "context exceeds model limit")
    make_rows = _v41_rows if adapter == "v41" else _v4_rows
    argument = config_path if adapter == "v41" else config
    rows = make_rows(argument, options, phase, past, tokens, batch, variant)
    if trace is not None:
        rows = _apply_trace(rows, trace)
    rows = _validate_ops(_with_dependencies(rows))
    config_hash = digest(config_path)
    metadata = {
        "model_id": model, "model_revision": options.get("model_revision", "sha256:" + config_hash),
        "config_sha256": config_hash, "model_config": path_label(config_path), "stage": phase, "batch": batch,
        "past_tokens": past, "query_tokens": tokens, "schedule": options["schedule"], "adapter": adapter,
        "routing_policy": options["routing_policy"], "variant": variant,
    }
    key = {k: v for k, v in metadata.items() if k != "model_config"}
    return {"schema_version": SCHEMA_VERSION, "workload_id": identity("workload", [key, rows]),
            "metadata": metadata, "operators": rows,
            "scope_exclusions": ["softmax", "routing selection", "elementwise operations", "collective communication"]}


def validate_workload(workload):
    versioned(workload, "workload")
    require(isinstance(workload["workload_id"], str) and workload["workload_id"], "invalid workload_id")
    return dict(workload, operators=_validate_ops(workload["operators"]))


def reference_diff(left, right):
    """Compare two explicit execution variants by stable operator ID."""
    a = {op["op_id"]: op for op in left["operators"]}
    b = {op["op_id"]: op for op in right["operators"]}
    result = []
    for op_id in sorted(a.keys() | b.keys()):
        x, y = a.get(op_id, {}), b.get(op_id, {})
        fields = ("precision_label", "useful_macs", "historical_macs", "shape")
        changes = [field for field in fields if x.get(field) != y.get(field)]
        if changes:
            result.append({"op_id": op_id, "changes": changes,
                           "current_precision": x.get("precision_label"), "alternate_precision": y.get("precision_label"),
                           "current_useful_macs": x.get("useful_macs"), "alternate_useful_macs": y.get("useful_macs"),
                           "current_historical_macs": x.get("historical_macs"),
                           "alternate_historical_macs": y.get("historical_macs")})
    return result
