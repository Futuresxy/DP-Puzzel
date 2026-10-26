"""Capture actual first-layer operator inputs with pinned, sliced BF16 weights."""
import argparse
import hashlib
import importlib.metadata
from pathlib import Path
import platform

from common import HERE, ROOT, inventory, read_json, sha256, write_json, write_mem
from weights import WeightReader


def load_module(module, prefix, reader):
    state = {name: reader.tensor(prefix + "." + name) for name, _ in module.named_parameters()}
    module.load_state_dict(state, strict=True, assign=True)
    return module.eval()


def statistics(values):
    import numpy as np
    x = values.detach().float().cpu().numpy().astype(np.float64)
    absolute = np.abs(x)
    return dict(shape=list(x.shape), min=float(x.min()), max=float(x.max()),
                abs_max=float(absolute.max()), rms=float(np.sqrt(np.mean(x * x))),
                zero_fraction=float(np.mean(x == 0)),
                absolute_quantiles={str(q): float(np.quantile(absolute, q)) for q in (0.5, 0.9, 0.99, 0.999)})


def save_bf16(path, tensor):
    import numpy as np
    import torch
    if tensor.dtype != torch.bfloat16 or not torch.isfinite(tensor).all():
        raise ValueError("Expected finite native BF16 capture")
    np.save(path, tensor.detach().contiguous().view(torch.uint16).cpu().numpy(), allow_pickle=False)


def text_tokens(source, cache, length):
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer
    registry = read_json(HERE / "sources.json")
    dataset = registry["dataset"]
    path = cache / "wikitext2-test" / dataset["file"]
    rows = pq.read_table(path, columns=["text"]).column("text").to_pylist()
    text = "\n\n".join(row for row in rows if row.strip())
    directory = cache / source["cache_name"]
    tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True, trust_remote_code=False)
    ids = tokenizer(text, add_special_tokens=False, truncation=False, verbose=False)["input_ids"][:length]
    if len(ids) != length:
        raise ValueError("Insufficient corpus tokens")
    metadata = dict(dataset=dataset, dataset_sha256=sha256(path),
                    joined_text_utf8_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    sequence_token_start=0, sequence_length=length, add_special_tokens=False,
                    tokenizer_files=[dict(path=name, sha256=sha256(directory / name))
                                     for name in ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt")
                                     if (directory / name).exists()])
    return ids, metadata


def capture(name, source, args, setting):
    import numpy as np
    import torch
    from transformers import AutoConfig
    if source["layer"] != 0:
        raise ValueError("This small-download collector only supports layer 0")
    output = args.output / "raw" / name
    if output.exists():
        raise ValueError(f"Refusing to overwrite capture: {output}")
    reader = WeightReader(source, args.cache, HERE / "cache" / "weight-ranges")
    ids, corpus = text_tokens(source, args.cache, setting["sequence_length"])
    print(f"{name}: reading {len(set(ids))} unique token embedding rows", flush=True)
    embedding = reader.tensor("model.embed_tokens.weight", rows=ids)
    config = AutoConfig.from_pretrained(args.cache / source["cache_name"], local_files_only=True)
    config._attn_implementation = "eager"
    prefix = "model.layers.0"
    lower = setting["minimum_token_position"]
    count = setting["m"]
    routing = None
    if name == "qwen_qproj":
        from transformers.models.qwen2.modeling_qwen2 import Qwen2RMSNorm
        norm = load_module(Qwen2RMSNorm(config.hidden_size, config.rms_norm_eps), prefix + ".input_layernorm", reader)
        activation = norm(embedding)
        weight = reader.tensor(prefix + ".self_attn.q_proj.weight")
        bias = reader.tensor(prefix + ".self_attn.q_proj.bias")
        positions = np.linspace(lower, len(ids) - 1, count, dtype=np.int64).tolist()
        pool_positions = list(range(len(ids)))
        operator = prefix + ".self_attn.q_proj"
        expert = None
    else:
        from transformers.models.qwen2_moe.modeling_qwen2_moe import (
            Qwen2MoeAttention, Qwen2MoeRMSNorm, Qwen2MoeRotaryEmbedding)
        from transformers.activations import ACT2FN
        print(f"{name}: reading first-layer attention and router weights", flush=True)
        norm = load_module(Qwen2MoeRMSNorm(config.hidden_size, config.rms_norm_eps), prefix + ".input_layernorm", reader)
        attention = load_module(Qwen2MoeAttention(config, layer_idx=0).to(torch.bfloat16), prefix + ".self_attn", reader)
        postnorm = load_module(Qwen2MoeRMSNorm(config.hidden_size, config.rms_norm_eps), prefix + ".post_attention_layernorm", reader)
        hidden = embedding.unsqueeze(0)
        position_ids = torch.arange(len(ids)).unsqueeze(0)
        rotary = Qwen2MoeRotaryEmbedding(config)
        mask = torch.full((len(ids), len(ids)), torch.finfo(torch.bfloat16).min, dtype=torch.bfloat16).triu(1)[None, None]
        attended, _ = attention(norm(hidden), attention_mask=mask, position_ids=position_ids,
                                position_embeddings=rotary(hidden, position_ids), use_cache=False)
        hidden = postnorm(hidden + attended).reshape(-1, config.hidden_size)
        router_weight = reader.tensor(prefix + ".mlp.gate.weight")
        logits = torch.nn.functional.linear(hidden, router_weight)
        probabilities, selected = torch.topk(torch.softmax(logits, dim=-1, dtype=torch.float32),
                                            config.num_experts_per_tok, dim=-1)
        if config.norm_topk_prob:
            probabilities = probabilities / probabilities.sum(dim=-1, keepdim=True)
        hit_counts = torch.bincount(selected[lower:].flatten(), minlength=config.num_experts).tolist()
        eligible = sorted((hits, idx) for idx, hits in enumerate(hit_counts) if hits >= count)
        if not eligible:
            raise ValueError("No expert with enough genuinely routed tokens")
        _, expert = eligible[(len(eligible) - 1) // 2]
        pool_positions = torch.where((selected == expert).any(dim=1))[0].tolist()
        candidates = [pos for pos in pool_positions if pos >= lower]
        positions = [candidates[i] for i in np.linspace(0, len(candidates) - 1, count, dtype=np.int64)]
        print(f"{name}: selected expert {expert}, {len(pool_positions)} routed tokens; sample {positions}", flush=True)
        ep = prefix + f".mlp.experts.{expert}"
        gate = reader.tensor(ep + ".gate_proj.weight")
        up = reader.tensor(ep + ".up_proj.weight")
        routed = hidden[pool_positions]
        # This is precisely the selected expert's official MLP input to down_proj;
        # other experts and router-weighted output reduction are not dependencies.
        activation = ACT2FN[config.hidden_act](torch.nn.functional.linear(routed, gate)) * torch.nn.functional.linear(routed, up)
        weight = reader.tensor(ep + ".down_proj.weight")
        bias = None
        operator = ep + ".down_proj"
        routing = dict(expert_id=expert, hit_counts_after_warmup=hit_counts,
                       median_rule="lower median of eligible (hit_count, expert_id), count >= M",
                       selected_experts=selected.tolist(), routing_probabilities=probabilities.tolist(),
                       routed_pool_positions=pool_positions)
    # One channel from each equal output-channel stratum (one/head for Q).
    channels = [((2 * i + 1) * weight.shape[0]) // (2 * setting["n"]) for i in range(setting["n"])]
    pool_indices = [pool_positions.index(position) for position in positions]
    start, k = setting["k_start"], setting["k"]
    if start % 64 or start + k > weight.shape[1] or activation.shape[1] != weight.shape[1]:
        raise ValueError("Invalid K-aligned source interval")
    a = activation[pool_indices, start:start + k].contiguous()
    b = weight[channels, start:start + k].contiguous()
    output.mkdir(parents=True)
    save_bf16(output / "a_parent_bf16.npy", activation)
    save_bf16(output / "b_parent_bf16.npy", weight)
    save_bf16(output / "a_bf16.npy", a)
    save_bf16(output / "b_bf16.npy", b)
    np.save(output / "tokens.npy", np.asarray(ids, dtype=np.int64), allow_pickle=False)
    write_mem(output / "a_bf16.mem", a.view(torch.uint16).flatten().tolist(), 16)
    write_mem(output / "b_bf16.mem", b.view(torch.uint16).flatten().tolist(), 16)
    if bias is not None:
        save_bf16(output / "bias_bf16.npy", bias[channels])
    if routing is not None:
        write_json(output / "routing.json", routing)
    software = {package: importlib.metadata.version(package) for package in
                ("torch", "transformers", "numpy", "safetensors", "huggingface-hub", "pyarrow")}
    manifest = dict(schema_version=1, kind="ai_operator_capture", source_id=name, model=source,
                    operator=operator, expert_id=expert, corpus=corpus,
                    selection=dict(token_positions=positions, pool_indices=pool_indices,
                                   output_channels=channels, k_start=start, k=k),
                    shape=dict(m=count, n=setting["n"], k=k, parent_k=weight.shape[1]),
                    macs=count * setting["n"] * k, compute_dtype="bfloat16", device="cpu",
                    execution="official Transformers dependency slice of first layer; no full-model forward",
                    excluded="projection bias, router output weighting, other experts, C, subsequent layers",
                    settings=setting, sources_sha256=sha256(HERE / "sources.json"),
                    software=software, python=platform.python_version(), threads=args.threads,
                    parent_stats=dict(a=statistics(activation), b=statistics(weight)),
                    selected_stats=dict(a=statistics(a), b=statistics(b)),
                    weight_ranges=reader.provenance(),
                    files=inventory(output),
                    code_sha256={p.name: sha256(p) for p in (HERE / "collect.py", HERE / "weights.py", HERE / "common.py")})
    write_json(output / "manifest.json", manifest)
    print(f"{name}: captured {manifest['macs']} MAC; downloaded {reader.network_bytes} weight bytes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("all", "qwen_qproj", "moe_downproj"), default="all")
    parser.add_argument("--cache", type=Path, default=ROOT / ".deps")
    parser.add_argument("--output", type=Path, default=HERE / "artifacts" / "ai_wikitext2_l0_v1")
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.threads <= 32:
        parser.error("threads must be 1..32")
    import torch
    torch.set_num_threads(args.threads)
    torch.manual_seed(0)  # Module initialization is overwritten by checkpoint weights.
    torch.use_deterministic_algorithms(True)
    registry = read_json(HERE / "sources.json")
    names = registry["models"] if args.source == "all" else [args.source]
    with torch.inference_mode():
        for name in names:
            capture(name, registry["models"][name], args, registry["capture"])


if __name__ == "__main__":
    main()
