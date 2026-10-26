"""Validate captured/quantized files and FP64 references, not DUT correctness."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import math
from pathlib import Path
import struct

from common import HERE, read_json, sha256, verify_inventory, write_json
from formats import FORMATS
from golden import k_indices, load_memory, operands
from quantize import bf16_values, packed_words


def read_doubles(path):
    return [struct.unpack("<d", struct.pack("<Q", int(word, 16)))[0]
            for word in path.read_text().splitlines()]


def exact_dot(a, b):
    # An independent rational sum audits FP64 goldens without reproducing fsum.
    return float(sum((Fraction.from_float(float(x)) * Fraction.from_float(float(y))
                      for x, y in zip(a, b)), Fraction()))


def validate(corpus, summary_path):
    import numpy as np
    if not __debug__:
        raise RuntimeError("Run data validation without Python -O")
    registry = read_json(HERE / "sources.json")
    summary = dict(schema_version=1, kind="ai_data_preparation_evidence", total_macs_per_format=0,
                   generated_utc=datetime.now(timezone.utc).isoformat(),
                   artifact_path=str(corpus.relative_to(HERE)) if corpus.is_relative_to(HERE) else str(corpus),
                   sources_sha256=sha256(HERE / "sources.json"), sources=[],
                   limitations=["Software data checks only; no RTL simulation or PPA",
                                "C=0 partial-dot references; no feedback/rounding acceptance contract",
                                "Two first-layer excerpts from WikiText-2, not model-wide accuracy or power coverage",
                                "Large raw/generated data stay local under ignored artifacts; no remote archive URI yet"])
    checked_goldens = 0
    for source in registry["models"]:
        raw = corpus / "raw" / source
        capture = read_json(raw / "manifest.json")
        verify_inventory(raw, capture["files"])
        assert capture["sources_sha256"] == sha256(HERE / "sources.json")
        for file, fingerprint in capture["code_sha256"].items():
            assert sha256(HERE / file) == fingerprint
        shape = capture["shape"]
        assert shape == dict(m=4, n=16, k=768, parent_k=2048 if source == "qwen_qproj" else 1408)
        assert capture["macs"] == 49152 and capture["model"]["layer"] == 0
        for side, indices in (("a", capture["selection"]["pool_indices"]),
                              ("b", capture["selection"]["output_channels"])):
            parent = np.load(raw / f"{side}_parent_bf16.npy", allow_pickle=False)
            selected = np.load(raw / f"{side}_bf16.npy", allow_pickle=False)
            start = capture["selection"]["k_start"]
            assert np.array_equal(selected, parent[indices, start:start + 768])
        entry = dict(id=source, model=capture["model"], operator=capture["operator"],
                     expert_id=capture["expert_id"], selection=capture["selection"],
                     macs=capture["macs"], selected_stats=capture["selected_stats"],
                     raw_manifest_sha256=sha256(raw / "manifest.json"),
                     capture_weight_network_bytes=capture["weight_ranges"]["network_bytes"], formats=[])
        for name, f in FORMATS.items():
            directory = corpus / "quantized" / source / name
            quant = read_json(directory / "manifest.json")
            verify_inventory(directory, quant["files"])
            for file, fingerprint in quant["code_sha256"].items():
                assert sha256(HERE / file) == fingerprint
            assert quant["source_manifest_sha256"] == entry["raw_manifest_sha256"]
            for side in ("a", "b"):
                get = lambda role: load_memory(directory, quant["memories"][f"{side}.{role}"])
                codes = get("elements")
                assert np.array_equal(get("words"), packed_words(codes, name))
                if f.bits == 6:
                    assert np.all((get("words") & 0xc0c0) == 0)
                if name == "bf16":
                    assert np.array_equal(codes, np.load(raw / f"{side}_bf16.npy", allow_pickle=False))
                if name == "hif4":
                    assert np.all(get("g0") <= 1) and np.all(get("g1") <= 1)
                if name == "nvfp4":
                    global_bits = int(get("global_scale")[0])
                    assert struct.unpack("<f", struct.pack("<I", global_bits))[0] == quant["global_scale"][side]
            a, b = operands(directory, quant)
            assert np.isfinite(a).all() and np.isfinite(b).all()
            gd = corpus / "golden" / source / name
            golden = read_json(gd / "manifest.json")
            verify_inventory(gd, golden["files"])
            for file, fingerprint in golden["code_sha256"].items():
                assert sha256(HERE / file) == fingerprint
            assert golden["quantized_manifest_sha256"] == sha256(directory / "manifest.json")
            full = read_doubles(gd / "dot_full_fp64.mem")
            exact = [exact_dot(ar, br) for ar in a for br in b]
            assert full == exact
            checked_goldens += len(full)
            for case in golden["cases"]:
                native = case["native_k"]
                index = k_indices(name, native, shape["k"])
                stored = [int(word, 16) for word in (gd / case["index_path"]).read_text().splitlines()]
                assert stored == [i for chunk in index for i in chunk]
                assert sorted(stored) == list(range(shape["k"]))
                partial = read_doubles(gd / case["golden_path"])
                expected = [math.fsum(float(ar[i]) * float(br[i]) for i in chunk)
                            for ar in a for br in b for chunk in index]
                assert partial == expected and len(partial) == case["transactions"]
                assert case["macs"] == 49152
                # Audit every chunk of one output with the rational oracle too.
                for chunk, got in zip(index, partial[:len(index)]):
                    assert got == exact_dot(a[0, chunk], b[0, chunk])
                    checked_goldens += 1
            entry["formats"].append(dict(format=name, quantized_manifest_sha256=sha256(directory / "manifest.json"),
                                          golden_manifest_sha256=sha256(gd / "manifest.json"),
                                          errors=quant["quantization_error_vs_source"], global_scale=quant["global_scale"],
                                          native_ks=[case["native_k"] for case in golden["cases"]]))
        summary["sources"].append(entry)
        summary["total_macs_per_format"] += capture["macs"]
    assert summary["total_macs_per_format"] == 98304
    summary["rational_oracle_checks"] = checked_goldens
    summary["status"] = "software_data_checks_passed"
    summary["validator_sha256"] = sha256(HERE / "validate.py")
    write_json(summary_path, summary)
    print(f"Validated 2 sources × {len(FORMATS)} formats; 98,304 MAC/format; {checked_goldens} rational golden checks")
    print(f"Evidence: {summary_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=HERE / "artifacts" / "ai_wikitext2_l0_v1")
    parser.add_argument("--summary", type=Path, default=HERE / "ai-first-layer-summary.json")
    args = parser.parse_args()
    validate(args.corpus, args.summary)


if __name__ == "__main__":
    main()
