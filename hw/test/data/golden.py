"""Unrounded FP64 dot references for file-driven replay, with C=0 explicitly."""
import argparse
import math
from pathlib import Path
import struct

from common import HERE, inventory, read_json, sha256, verify_inventory, write_json, write_mem
from formats import FORMATS, dequantize


def load_memory(directory, descriptor):
    import numpy as np
    values = [int(word, 16) for word in (directory / descriptor["path"]).read_text().splitlines()]
    if len(values) != descriptor["count"] or any(value >= 1 << descriptor["bits"] for value in values):
        raise ValueError("Malformed memory file")
    dtype = np.uint16 if descriptor["bits"] <= 16 else np.uint64
    return np.array(values, dtype=dtype).reshape(descriptor["shape"])


def operands(directory, manifest, include_global=False):
    result = []
    for side in ("a", "b"):
        def get(role):
            key = f"{side}.{role}"
            return load_memory(directory, manifest["memories"][key]) if key in manifest["memories"] else None
        result.append(dequantize(get("elements"), manifest["format"], get("scales"), get("g0"), get("g1"),
                                 manifest["global_scale"][side] if include_global else 1.0))
    return result


def k_indices(name, native_k, full_k):
    """Same paired A/B permutation; preserve original HiF4 64-element roots."""
    if full_k % native_k:
        raise ValueError("Native K must divide the source row")
    if name == "hif4" and native_k == 96:
        result = []
        for start in range(0, full_k, 192):
            result.append(list(range(start, start + 96)))
            result.append(list(range(start + 128, start + 192)) + list(range(start + 96, start + 128)))
        return result
    return [list(range(start, start + native_k)) for start in range(0, full_k, native_k)]


def double_bits(value):
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def build(directory, output):
    manifest = read_json(directory / "manifest.json")
    verify_inventory(directory, manifest["files"])
    name = manifest["format"]
    a, b = operands(directory, manifest)
    m, full_k = a.shape
    n = len(b)
    if output.exists():
        raise ValueError(f"Refusing to overwrite golden: {output}")
    output.mkdir(parents=True)
    full = [math.fsum(float(x) * float(y) for x, y in zip(ar, br)) for ar in a for br in b]
    write_mem(output / "dot_full_fp64.mem", map(double_bits, full), 64)
    # Domain including NV global factors is a separate diagnostic, never fed
    # straight to the PE's internal-domain scoreboard or multiplied over C.
    domain = manifest["global_scale"]["a"] * manifest["global_scale"]["b"]
    if name == "nvfp4":
        write_mem(output / "dot_source_domain_fp64.mem", (double_bits(value * domain) for value in full), 64)
    if FORMATS[name].bits == 16:
        native_ks = [16, 32, 48, 64]
    elif FORMATS[name].bits >= 6:
        native_ks = [32, 64, 96, 128]
    else:
        native_ks = [32, 64, 96, 128, 192, 256]
    cases = []
    for native in native_ks:
        indices = k_indices(name, native, full_k)
        target = output / f"k{native}"
        target.mkdir()
        write_mem(target / "k_index.mem", (index for chunk in indices for index in chunk), 16)
        partials = [math.fsum(float(ar[index]) * float(br[index]) for index in chunk)
                    for ar in a for br in b for chunk in indices]
        write_mem(target / "dot_fp64.mem", map(double_bits, partials), 64)
        cases.append(dict(native_k=native, chunks_per_output=len(indices), transactions=len(partials),
                          macs=len(partials) * native, order="m, n, chunk; chunk innermost",
                          c="FP32 +0 for each independent partial dot",
                          index_path=f"k{native}/k_index.mem", golden_path=f"k{native}/dot_fp64.mem"))
    write_json(output / "manifest.json", dict(schema_version=1, kind="software_dot_golden", format=name,
               source_id=manifest["source_id"], quantized_manifest_sha256=sha256(directory / "manifest.json"),
               arithmetic="exact binary decoding; binary64 products; math.fsum; retain unrounded binary64",
               numeric_domain="PE-local element and block scales; excludes NVFP4 global factors",
               full_shape=[m, n], full_k=full_k, cases=cases,
               not_defined="FP32 C feedback, bias, rounding-mode acceptance and ULP threshold are later contracts",
               code_sha256={p.name: sha256(p) for p in (HERE / "golden.py", HERE / "formats.py", HERE / "common.py")},
               files=inventory(output)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=HERE / "artifacts" / "ai_wikitext2_l0_v1")
    args = parser.parse_args()
    for source in read_json(HERE / "sources.json")["models"]:
        for name in FORMATS:
            build(args.corpus / "quantized" / source / name, args.corpus / "golden" / source / name)
            print(f"{source}/{name}: FP64 dot golden ready", flush=True)


if __name__ == "__main__":
    main()
