"""Convert one captured AI corpus into nine same-source numeric encodings."""
import argparse
from pathlib import Path
import struct

from common import HERE, inventory, read_json, sha256, verify_inventory, write_json, write_mem
from formats import FORMATS, SEMANTICS, dequantize, f32, quantize_rows


def bf16_values(bits):
    import numpy as np
    return (np.asarray(bits, dtype=np.uint32) << 16).view(np.float32).astype(np.float64)


def lanes_per_word(name):
    return 1 if FORMATS[name].bits == 16 else 2 if FORMATS[name].bits >= 6 else 4


def packed_words(codes, name):
    import numpy as np
    lanes = lanes_per_word(name)
    words = np.zeros((len(codes), codes.shape[1] // lanes), dtype=np.uint16)
    for lane in range(lanes):
        words |= codes[:, lane::lanes] << (lane * (16 // lanes))
    return words


def quantize_source(raw, output, name):
    import numpy as np
    capture = read_json(raw / "manifest.json")
    verify_inventory(raw, capture["files"])
    target = output / capture["source_id"] / name
    if target.exists():
        raise ValueError(f"Refusing to overwrite quantization: {target}")
    start, k = capture["selection"]["k_start"], capture["shape"]["k"]
    f = FORMATS[name]
    values, globals_, shapes = {}, {}, {}
    for side, indices in (("a", capture["selection"]["pool_indices"]),
                          ("b", capture["selection"]["output_channels"])):
        parent = bf16_values(np.load(raw / f"{side}_parent_bf16.npy", allow_pickle=False))
        peak = float(np.max(np.abs(parent)))
        global_scale = f32(peak / (448 * 6)) if name == "nvfp4" and peak else 1.0
        quant = quantize_rows(parent[indices], name, global_scale)
        quant["codes"] = quant["codes"][:, start:start + k].copy()
        if quant["scales"] is not None:
            quant["scales"] = quant["scales"][:, start // f.block:(start + k) // f.block].copy()
        if name == "hif4":
            quant["g0"] = quant["g0"][:, start // 4:(start + k) // 4].copy()
            quant["g1"] = quant["g1"][:, start // 8:(start + k) // 8].copy()
        values[side] = quant
        globals_[side] = global_scale
        shapes[side] = list(quant["codes"].shape)
    target.mkdir(parents=True)
    memories = {}
    errors = {}
    for side, quant in values.items():
        codes = quant["codes"]
        streams = {"elements": (codes, f.bits), "words": (packed_words(codes, name), 16)}
        if f.scale != "none":
            streams["scales"] = (quant["scales"], 8)
        if name == "hif4":
            streams["g0"] = (quant["g0"], 1)
            streams["g1"] = (quant["g1"], 1)
        for role, (array, width) in streams.items():
            file = f"{side}.{role}.mem"
            write_mem(target / file, array.flatten(), width)
            memories[f"{side}.{role}"] = dict(path=file, bits=width, count=array.size,
                                              shape=list(array.shape), order="row-major; K innermost")
        if name == "nvfp4":
            bits = struct.unpack("<I", struct.pack("<f", globals_[side]))[0]
            file = f"{side}.global_scale.mem"
            write_mem(target / file, [bits], 32)
            memories[f"{side}.global_scale"] = dict(path=file, bits=32, count=1, shape=[1], encoding="IEEE binary32")
        # Both domains are explicit: the hardware consumes local block scaling;
        # global_scale belongs to source-domain reconstruction outside this PE.
        reconstructed = dequantize(codes, name, quant["scales"], quant["g0"], quant["g1"], globals_[side])
        original = bf16_values(np.load(raw / f"{side}_bf16.npy", allow_pickle=False))
        errors[side] = dict(max_abs_error=float(np.max(np.abs(reconstructed - original))),
                           rmse=float(np.sqrt(np.mean((reconstructed - original) ** 2))),
                           zero_elements=int(np.count_nonzero(reconstructed == 0)))
    manifest = dict(schema_version=1, kind="ai_quantized_operands", source_id=capture["source_id"],
                    format=name, element_bits=f.bits, block_size=f.block, scale_format=f.scale,
                    shapes=shapes, macs=capture["macs"], semantics=SEMANTICS,
                    rounding="RNE, ties to even encoded significand; finite saturation",
                    global_scale=globals_, nvfp4_scale_scope="original captured parent tensors",
                    lanes_per_word=lanes_per_word(name), lowest_k_lane="least significant lane",
                    fp6_storage="low six bits of each byte; high two bits zero" if f.bits == 6 else None,
                    source_manifest_sha256=sha256(raw / "manifest.json"),
                    source_selection=capture["selection"], memories=memories,
                    quantization_error_vs_source=errors, files=inventory(target),
                    code_sha256={p.name: sha256(p) for p in (HERE / "quantize.py", HERE / "formats.py", HERE / "common.py")})
    write_json(target / "manifest.json", manifest)
    print(f"{capture['source_id']}/{name}: {capture['macs']} MAC source, quantized", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=HERE / "artifacts" / "ai_wikitext2_l0_v1")
    parser.add_argument("--format", choices=["all", *FORMATS], default="all")
    args = parser.parse_args()
    names = FORMATS if args.format == "all" else [args.format]
    sources = read_json(HERE / "sources.json")["models"]
    for source in sources:
        for name in names:
            quantize_source(args.corpus / "raw" / source, args.corpus / "quantized", name)


if __name__ == "__main__":
    main()
