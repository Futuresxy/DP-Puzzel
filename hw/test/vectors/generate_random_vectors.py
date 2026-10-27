#!/usr/bin/env python3
"""Generate 1024 AB/scale + 64 special + 512 C tests per format/K as logical TXT."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import tempfile

from exact_dot import (FORMATS, FP32, GOLDEN_MODEL, SCALE_TYPES, Operand,
                       decode_binary, dot_product, exact_sum, finite, fp32_class,
                       round_fp32, serialize, shape)


ROOT = Path(__file__).resolve().parents[3]
DATASET = "random_1600"
AB_SCENARIOS = (
    "normal_normal_local", "normal_normal_full", "normal_subnormal",
    "subnormal_normal", "subnormal_subnormal", "mixed_local",
    "normal_normal_scale_edges", "mixed_scale_spread",
)
C_SCENARIOS = (
    "c_zero", "c_comparable_same_sign", "c_comparable_opposite_sign",
    "c_exact_cancellation", "c_near_cancellation", "c_dominant", "c_tiny",
    "c_subnormal",
)
SEGMENTS = (
    ("ab_scale_random", 1024, True, False),
    ("special_directed", 64, False, True),
    ("c_stratified_random", 512, True, False),
)
REFERENCES = {
    "ocp_mx": "https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf",
    "hif4": "https://arxiv.org/html/2602.11287v2#S2.SS1",
    "nvfp4_scope": "Unsigned E4M3 block scales; external tensor scales fixed to 1",
}


def unit_code(name):
    fmt = FORMATS[name]
    return 4 if name == "hif4" else fmt.bias << fmt.frac_bits


def unit_scale(name):
    return {"none": 0, "e8m0": 127, "ue4m3": 0x38, "e6m2": 0xC0}[FORMATS[name].scale_kind]


def unit_operand(name, k):
    ns, ng0, ng1 = shape(name, k)
    return Operand([unit_code(name)] * k, [unit_scale(name)] * ns, [0] * ng0, [0] * ng1)


def random_code(name, category, rng, regime="local", boost=False):
    fmt = FORMATS[name]
    sign = rng.getrandbits(1) << (fmt.bits - 1)
    if name == "hif4":
        # S1P2 lower/upper magnitudes are the explicit analogue of the two
        # strata; its E6M2 scale has no subnormal representation.
        return sign | (rng.randint(1, 3) if category == "subnormal" else rng.randint(4, 7))
    if category == "subnormal":
        return sign | rng.randint(1, (1 << fmt.frac_bits) - 1)
    max_exp = (1 << fmt.exp_bits) - (2 if fmt.specials == "ieee" else 1)
    if regime == "full":
        exponent = rng.randint(1, max_exp)
    elif regime == "edges":
        exponent = rng.choice((1, min(2, max_exp), max(1, max_exp - 1), max_exp))
    elif boost:
        exponent = rng.randint(max(1, max_exp - 6), max_exp)
    else:
        exponent = max(1, min(max_exp, fmt.bias + rng.randint(-8, 8)))
    max_fraction = (1 << fmt.frac_bits) - 1
    if fmt.specials == "nan_only" and exponent == max_exp:
        max_fraction -= 1
    return sign | (exponent << fmt.frac_bits) | rng.randint(0, max_fraction)


def random_scales(name, count, rng, regime):
    kind = FORMATS[name].scale_kind
    result = []
    for i in range(count):
        if regime == "full":
            raw = rng.randint(1, 126) if kind == "ue4m3" else rng.randint(0, 254)
        elif regime == "edges":
            edges = (1, 7, 8, 0x38, 0x78, 0x7E) if kind == "ue4m3" else (0, 1, 126, 127, 128, 253, 254)
            raw = edges[(i + rng.randrange(len(edges))) % len(edges)]
        elif kind == "e8m0":
            raw = 127 + (rng.choice((-64, -32, 0, 32, 64)) if regime == "spread" else rng.randint(-16, 16))
        elif kind == "ue4m3":
            raw = (rng.randint(1, 15) << 3) | rng.randrange(7) if regime == "spread" else (rng.randint(5, 9) << 3) | rng.randrange(8)
        else:
            raw = (rng.randint(0, 62) << 2) | rng.randrange(4) if regime == "spread" else (rng.randint(40, 56) << 2) | rng.randrange(4)
        result.append(raw)
    return result


def random_operand(name, k, rng, category="normal", regime="local", boost=False):
    ns, ng0, ng1 = shape(name, k)
    categories = [rng.choice(("normal", "subnormal")) if category == "mixed" else category for _ in range(k)]
    return Operand([random_code(name, c, rng, regime, boost) for c in categories],
                   random_scales(name, ns, rng, regime),
                   [rng.getrandbits(1) for _ in range(ng0)],
                   [rng.getrandbits(1) for _ in range(ng1)])


def ab_cases(name, k, rng):
    for scenario in AB_SCENARIOS:
        for _ in range(128):
            categories = {
                "normal_subnormal": ("normal", "subnormal"),
                "subnormal_normal": ("subnormal", "normal"),
                "subnormal_subnormal": ("subnormal", "subnormal"),
            }.get(scenario, ("mixed", "mixed") if scenario.startswith("mixed") else ("normal", "normal"))
            regime = "full" if scenario.endswith("full") else "edges" if scenario.endswith("edges") else "spread" if scenario.endswith("spread") else "local"
            boost = scenario in ("normal_subnormal", "subnormal_normal")
            yield (random_operand(name, k, rng, categories[0], regime, boost),
                   random_operand(name, k, rng, categories[1], regime, boost), 0, scenario)


def coherent_operands(name, k, rng):
    """Moderate random normal operands with a nonzero dot for meaningful C strata."""
    a, b = random_operand(name, k, rng), random_operand(name, k, rng)
    sign_bit = 1 << (FORMATS[name].bits - 1)
    negative_dot = rng.getrandbits(1) * sign_bit
    b.codes = [(v & (sign_bit - 1)) | ((a.codes[i] & sign_bit) ^ negative_dot)
               for i, v in enumerate(b.codes)]
    return a, b


def single_residual(name, a, b):
    """Cancel adjacent products inside the same 4-lane metadata group.

    One uncancelled product remains, so its exact negative is representable in
    FP32 for these moderate inputs. This exercises C cancellation without
    pretending an arbitrary exact dot can always be stored in a FP32 C.
    """
    sign_bit = 1 << (FORMATS[name].bits - 1)
    for i in range(0, len(a.codes) - 1, 2):
        a.codes[i + 1] = a.codes[i] ^ sign_bit
        b.codes[i + 1] = b.codes[i]
    if len(a.codes) > 1:
        a.codes[1] = 0
        if len(a.codes) % 2:
            a.codes[-1] = 0


def c_cases(name, k, rng):
    for scenario in C_SCENARIOS:
        for _ in range(64):
            a, b = coherent_operands(name, k, rng)
            if scenario in ("c_exact_cancellation", "c_near_cancellation"):
                single_residual(name, a, b)
            dot = dot_product(name, a, b)
            exponent = abs(dot.coefficient).bit_length() - 1 + dot.exponent
            sign = -1 if dot.coefficient < 0 else 1
            if scenario == "c_zero":
                c = 0
            elif scenario.startswith("c_comparable"):
                c = round_fp32(finite(sign * rng.randrange(1 << 23, 1 << 24), exponent - 23))
                if scenario.endswith("opposite_sign"):
                    c ^= 0x80000000
            elif scenario in ("c_exact_cancellation", "c_near_cancellation"):
                c = round_fp32(-dot)
                if decode_binary(FP32, c) != -dot:
                    raise ValueError("Cancellation fixture C is not exactly representable")
                if scenario == "c_near_cancellation":
                    c += rng.choice((-1, 1))  # adjacent representable FP32, away from zero/Inf
            elif scenario == "c_subnormal":
                c = (rng.getrandbits(1) << 31) | rng.randint(1, 0x7FFFFF)
            else:
                shift = 40 if scenario == "c_dominant" else -40
                c = round_fp32(finite(rng.choice((-1, 1)) * rng.randrange(1 << 23, 1 << 24), exponent + shift - 23))
            yield a, b, c, scenario


def special_cases(name, k):
    fmt = FORMATS[name]
    common = ("a_zero", "b_zero", "negative_zeros", "dot_cancellation",
              "c_qnan", "c_snan", "c_positive_inf", "c_negative_inf")
    if fmt.scale_kind == "none":
        extra = ("a_nan", "b_nan", "a_inf", "b_inf", "zero_times_inf",
                 "opposite_infinities", "inf_cancel_c", "negative_inf")
    elif fmt.specials == "ieee":
        extra = ("a_nan", "b_nan", "a_inf", "zero_times_inf", "opposite_infinities",
                 "a_scale_nan", "b_scale_nan", "minimum_scale")
    elif fmt.specials == "nan_only":
        extra = ("a_nan", "b_nan", "a_scale_nan", "b_scale_nan", "zero_nan_scale",
                 "inf_nan_scale", "minimum_scale", "cancel_with_c")
    elif fmt.scale_kind == "ue4m3":
        extra = ("a_scale_nan", "b_scale_nan", "zero_nan_scale", "a_scale_zero",
                 "b_scale_zero", "both_scales_zero", "minimum_scale", "maximum_scale")
    else:
        extra = ("a_scale_nan", "b_scale_nan", "zero_nan_scale", "inf_nan_scale",
                 "negative_inf_nan_scale", "minimum_scale", "maximum_scale", "cancel_with_c")
    sign_bit = 1 << (fmt.bits - 1)
    inf = ((1 << fmt.exp_bits) - 1) << fmt.frac_bits
    nan = inf | ((1 << fmt.frac_bits) - 1)
    scale_nan = 0x7F if fmt.scale_kind == "ue4m3" else 0xFF
    positions = (0, k // 2, k - 1, min(k - 1, fmt.block if fmt.block > 1 else 1))
    for scenario in common + extra:
        for variant, pos in enumerate(positions):
            a, b, c = unit_operand(name, k), unit_operand(name, k), 0
            slot = pos // fmt.block
            if scenario in ("a_zero", "b_zero", "negative_zeros"):
                target = b if scenario == "b_zero" else a
                target.codes = [sign_bit if scenario == "negative_zeros" else 0] * k
                if scenario == "negative_zeros":
                    c = 0x80000000
            elif scenario == "dot_cancellation":
                a.codes = [unit_code(name) | (sign_bit if i & 1 else 0) for i in range(k)]
                if k & 1:
                    a.codes[-1] = 0
            elif scenario in ("c_qnan", "c_snan"):
                c = (0x7FC00000 if scenario == "c_qnan" else 0x7F800000) | (variant + 1) | ((variant & 1) << 31)
            elif scenario in ("c_positive_inf", "c_negative_inf"):
                c = 0x7F800000 | (0x80000000 if scenario == "c_negative_inf" else 0)
            elif scenario in ("a_nan", "b_nan", "a_inf", "b_inf", "negative_inf"):
                target = b if scenario.startswith("b_") else a
                target.codes[pos] = nan if scenario.endswith("nan") else inf | (sign_bit if scenario == "negative_inf" else 0)
            elif scenario == "zero_times_inf":
                a.codes[pos], b.codes[pos] = 0, inf
            elif scenario == "opposite_infinities":
                a.codes[pos] = inf
                if k > 1:
                    a.codes[(pos + 1) % k] = inf | sign_bit
                else:
                    c = 0xFF800000
            elif scenario == "inf_cancel_c":
                a.codes[pos], c = inf, 0xFF800000
            elif scenario in ("a_scale_nan", "b_scale_nan"):
                (a if scenario.startswith("a_") else b).scales[slot] = scale_nan
            elif scenario in ("zero_nan_scale", "inf_nan_scale", "negative_inf_nan_scale"):
                a.scales[slot] = scale_nan
                if scenario == "zero_nan_scale":
                    a.codes = [0] * k
                else:
                    c = 0xFF800000 if scenario.startswith("negative") else 0x7F800000
            elif scenario in ("a_scale_zero", "b_scale_zero", "both_scales_zero"):
                if scenario != "b_scale_zero":
                    a.scales = [0] * len(a.scales)
                if scenario != "a_scale_zero":
                    b.scales = [0] * len(b.scales)
            elif scenario in ("minimum_scale", "maximum_scale"):
                raw = (1 if fmt.scale_kind == "ue4m3" else 0) if scenario == "minimum_scale" else (126 if fmt.scale_kind == "ue4m3" else 254)
                a.scales = [raw] * len(a.scales)
                if fmt.scale_kind == "e8m0":
                    b.scales = [254 - raw] * len(b.scales)  # finite exponent extremes without masking in FP32
            elif scenario == "cancel_with_c":
                c = round_fp32(-dot_product(name, a, b))
            else:
                raise ValueError(f"Unknown directed scenario: {scenario}")
            yield a, b, c, f"{scenario}:lane{pos}:variant{variant}"


def element_class(name, raw):
    fmt = FORMATS[name]
    if name == "hif4":
        return "s1p2_low" if raw & 7 < 4 else "s1p2_high"
    return "subnormal" if ((raw >> fmt.frac_bits) & ((1 << fmt.exp_bits) - 1)) == 0 and raw & ((1 << fmt.frac_bits) - 1) else "normal"


def write_case(root, name, k, seed):
    # Seed identity is stable across format selection, K selection and loop order.
    derived = int.from_bytes(hashlib.sha256(f"dp-exact-v1:{seed}:{name}:K{k}".encode()).digest(), "big")
    rng = random.Random(derived)
    fmt = FORMATS[name]
    ns, ng0, ng1 = shape(name, k)
    directory = root / name / f"K{k}" / DATASET
    directory.mkdir(parents=True)
    segments, offset = [], 0
    for label, count, precision, exact in SEGMENTS:
        segments.append(dict(dataset=label, start=offset, stop=offset + count, count=count,
                             include_in_precision_rate=precision, require_bit_exact=exact))
        offset += count
    meta = dict(schema_version="dp_pe_vectors_v2", format=name, dataset=DATASET,
                kind="random_exact_1600", txn_count=1600, logical_k=k,
                a_data_type=fmt.dtype, b_data_type=fmt.dtype,
                a_sf_type=SCALE_TYPES[fmt.scale_kind], b_sf_type=SCALE_TYPES[fmt.scale_kind],
                c_type=0, out_type=0, rm=0, a_scale_count=ns, b_scale_count=ns,
                group0_count=ng0, group1_count=ng1, seed=seed,
                golden_model=GOLDEN_MODEL, acceptance_policy="fp32_steps_le2_special_exact_v1",
                precision_txn_count=1536, segments=segments,
                sources=["hw/test/vectors/generate_random_vectors.py"], references=REFERENCES,
                distribution=dict(kind="raw_encoding_stratified_v1", no_dut_result_filtering=True,
                                  hif4_strata="S1P2 high/low magnitudes; E6M2 normal scales only",
                                  c_fixture="coherent product signs; paired cancellation retains one product"),
                zero_policy="exact zero/cancellation -> +0; negative nonzero underflow -> -0",
                nan_policy="all NaNs -> canonical quiet FP32 7fc00000")
    header = [1600, k, fmt.dtype, fmt.dtype, SCALE_TYPES[fmt.scale_kind], SCALE_TYPES[fmt.scale_kind],
              0, 0, 0, ns, ns, ng0, ng1]
    labels, coverage, exact_results = [], [], []
    streams = (ab_cases(name, k, rng), special_cases(name, k), c_cases(name, k, rng))
    with (directory / "inputs.txt").open("w") as inputs, (directory / "golden.txt").open("w") as golden:
        inputs.write("PE_VECTORS_V2\n" + " ".join(map(str, header)) + "\n")
        txn = 0
        for segment, stream in zip(segments, streams):
            classes, outputs, a_scales, b_scales = Counter(), Counter(), Counter(), Counter()
            for a, b, c, label in stream:
                exact = exact_sum((dot_product(name, a, b), decode_binary(FP32, c)))
                result = round_fp32(exact)
                tokens = [f"{txn:08x}", f"{c:08x}"]
                tokens += [f"{v:04x}" for v in a.codes + b.codes]
                tokens += [f"{v:02x}" for v in a.scales + b.scales]
                tokens += [str(v) for v in a.group0 + b.group0 + a.group1 + b.group1]
                inputs.write(" ".join(tokens) + "\n")
                golden.write(f"{result:08x}\n")
                if segment["dataset"] != "special_directed":
                    classes.update(element_class(name, raw) for raw in a.codes + b.codes)
                outputs[fp32_class(result)] += 1
                a_scales.update(a.scales)
                b_scales.update(b.scales)
                labels.append(label)
                exact_results.append(serialize(exact))
                txn += 1
            if txn != segment["stop"]:
                raise ValueError("Generated segment length mismatch")
            coverage.append(dict(dataset=segment["dataset"], element_classes=dict(classes),
                                 golden_classes=dict(outputs),
                                 a_scale_codes={f"{v:02x}": n for v, n in sorted(a_scales.items())},
                                 b_scale_codes={f"{v:02x}": n for v, n in sorted(b_scales.items())}))
    meta.update(scenario_by_transaction=labels, coverage=coverage, exact_results=exact_results)
    (directory / "case.json").write_text(json.dumps(meta, indent=2) + "\n")
    return dict(format=name, k=k, dataset=DATASET, transactions=1600,
                path=directory.relative_to(root).as_posix(), kind=meta["kind"])


def default_ks(name):
    if FORMATS[name].scale_kind == "none":
        return (16,)
    return (32, 64, 96, 128) if FORMATS[name].bits in (6, 8) else (64, 96, 128, 192, 256)


def generate(output, names, ks=None, seed=0x5EED):
    groups = [(name, k) for name in names for k in (ks if ks is not None else default_ks(name))]
    if not groups or len(groups) != len(set(groups)):
        raise ValueError("Empty or duplicate format/K selection")
    for name, k in groups:
        shape(name, k)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"Refusing to overwrite existing corpus: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".exact-vectors-", dir=output.parent) as temporary:
        staging = Path(temporary) / "corpus"
        staging.mkdir()
        entries = [write_case(staging, name, k, seed) for name, k in groups]
        index = dict(schema_version="dp_pe_exact_corpus_v1", source_project="DP-Puzzel",
                     generator="hw/test/vectors/generate_random_vectors.py", generator_version=1,
                     golden_model=GOLDEN_MODEL, seed=seed, default_precision_dataset=DATASET,
                     format_k_groups=len(entries), case_count=len(entries), cases=entries)
        (staging / "index.json").write_text(json.dumps(index, indent=2) + "\n")
        staging.rename(output)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formats", "--format", nargs="+", choices=tuple(FORMATS), default=list(FORMATS))
    parser.add_argument("--k", nargs="+", type=int, help="logical K values; defaults follow each precision family")
    parser.add_argument("--seed", type=lambda s: int(s, 0), default=0x5EED)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or ROOT / "hw/test/vectors/generated" / f"random_1600_seed{args.seed}"
    try:
        index = generate(output, args.formats, args.k, args.seed)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Generation rejected: {error}\n")
    print(json.dumps(dict(output_root=str(output.resolve()), cases=index["case_count"],
                          transactions=index["case_count"] * 1600, golden_model=GOLDEN_MODEL), indent=2))


if __name__ == "__main__":
    main()
