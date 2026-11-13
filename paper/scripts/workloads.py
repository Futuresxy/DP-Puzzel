"""Analytical useful GEMM work; no engine timing or inference execution."""
import csv
import gzip
import json
from pathlib import Path
import deepseek_v41 as v41
SOURCE = Path(__file__).resolve().parents[1]/"data/inputs/models"
def v4_work(config, past, count, batch=1, phase="prefill", profile="paper_native"):
    """Full V4 backbone, useful sparse attention pairs, no MTP/DSpark.

    Native indexer counts causally valid pairs; reference indexer actually
    constructs the full prompt rectangle before masking. Other sparse attention
    work excludes padding/invalid positions in both profiles.
    """
    if phase not in ("prefill", "decode") or profile not in ("paper_native", "reference"):
        raise ValueError("Unknown phase/profile")
    if any(type(x) is not int or x < 0 for x in (past, count)) or type(batch) is not int or batch < 1:
        raise ValueError("Invalid token or batch count")
    if not count:
        return []
    c = config
    d, h, hd, q = (c[k] for k in ("dim", "n_heads", "head_dim", "q_lora_rank"))
    groups, o, ff = (c[k] for k in ("o_groups", "o_lora_rank", "moe_inter_dim"))
    ih, idim, hc = (c[k] for k in ("index_n_heads", "index_head_dim", "hc_mult"))
    tokens = batch*count
    rows = []

    def add(layer, kernel, precision, flops, basis):
        rows.append(dict(layer_id=layer, kernel=kernel, precision=precision,
                         flops=int(flops), basis=basis))

    def linear(layer, kernel, precision, n, k, multiplicity=1):
        add(layer, kernel, precision, 2*tokens*n*k*multiplicity,
            f"2*B*T*{n}*{k}*{multiplicity}")

    for layer, ratio in enumerate(c["compress_ratios"][:c["n_layers"]]):
        for name, n, k in (("q_down", q, d), ("q_up", h*hd, q),
                           ("window_kv", hd, d), ("o_final", d, groups*o)):
            linear(layer, name, "FP8", n, k)
        linear(layer, "o_group", "BF16", o, h*hd//groups, groups)
        pairs = v41.visible_pairs(past, count, 1, c["window_size"])
        if ratio:
            pairs += v41.visible_pairs(past, count, ratio, c["index_topk"] if ratio == 4 else None)
        for op in ("qk", "pv"):
            add(layer, "attention."+op, "BF16", 2*batch*h*hd*pairs,
                f"2*B*{h}*{hd}*valid_pairs({pairs})")
        for group, multiplicity in (("routed", c["n_activated_experts"]), ("shared", c["n_shared_experts"])):
            for op in ("gate", "up", "down"):
                linear(layer, "moe."+group+"."+op, "FP8", d, ff, multiplicity)
        linear(layer, "moe.router", "FP32", c["n_routed_experts"], d)
        for sublayer in ("attention", "ffn"):
            linear(layer, "mhc."+sublayer, "FP32", hc*(hc+2), hc*d)
        if ratio:
            width = hd*(2 if ratio == 4 else 1)
            for op in ("kv", "gate"):
                linear(layer, "compressor."+op, "FP32", width, d)
        if ratio == 4:
            linear(layer, "index.q_projection", "FP8", ih*idim, q)
            linear(layer, "index.head_weights", "BF16", ih, d)
            for op in ("kv", "gate"):
                linear(layer, "index.compressor."+op, "FP32", 2*idim, d)
            ipairs = (count*((past+count)//ratio) if profile == "reference" and phase == "prefill"
                      else v41.visible_pairs(past, count, ratio))
            add(layer, "index.qk", "FP4" if profile == "paper_native" else "BF16",
                2*batch*ih*idim*ipairs, f"2*B*{ih}*{idim}*index_pairs({ipairs})")
    add(-1, "hc_head", "FP32", 2*tokens*hc*hc*d, "2*B*T*hc*hc*d")
    logits = 1 if phase == "prefill" else count
    add(-1, "lm_head", "FP32", 2*batch*logits*d*c["vocab_size"], "2*B*N_logits*d*vocab")
    return rows

def work(model, phase, length, batch=1, profile="paper_native", decode_steps=1):
    if model == "DeepSeek-V4.1-Flash":
        options = dict(config=v41.load_config(SOURCE/model/"inference/config.json"), batch=batch, indexer="native" if profile == "paper_native" else "reference")
        if phase == "prefill":
            rows = v41.prefill_work(length, prefill_schedule="ced" if profile == "paper_native" else "full", **options)
        else:
            rows = v41.decode_work(length, decode_steps, **options)
        return [dict(layer_id=r["layer_id"], kernel=r["kernel"], precision=r["precision"],
                     flops=r["flops"], basis=r["formula"]+"; "+r["segment"]) for r in rows]
    config = json.loads((SOURCE/model/"inference/config.json").read_text())
    return v4_work(config, 0 if phase == "prefill" else length,
                   length if phase == "prefill" else decode_steps, batch, phase, profile)

def write_csv(path, rows):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "wt", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
