"""Independent exact decoding, dot products and one final FP32 RNE conversion.

Finite values are signed arbitrary-precision integers times powers of two.
No floating-point operations, RTL imports, alignment windows or DUT rounding
steps are used. Exact cancellation/all-zero sums produce canonical +0, as in
the public DP contract; a negative nonzero value rounding to zero retains -0.
"""
from dataclasses import dataclass
from typing import Iterable


GOLDEN_MODEL = "integer_dyadic_dot_plus_c_rne_fp32_v1"
CANONICAL_NAN = 0x7FC00000


@dataclass(frozen=True)
class Dyadic:
    coefficient: int = 0
    exponent: int = 0
    special: str = ""  # "", "nan", "inf"; infinity sign is coefficient +/-1.

    def __neg__(self):
        return Dyadic(-self.coefficient, self.exponent, self.special)


ZERO = Dyadic()
ONE = Dyadic(1)
NAN = Dyadic(special="nan")


def finite(coefficient: int, exponent: int = 0) -> Dyadic:
    if coefficient == 0:
        return ZERO
    magnitude = abs(coefficient)
    trailing = (magnitude & -magnitude).bit_length() - 1
    return Dyadic(coefficient >> trailing, exponent + trailing)


def multiply(a: Dyadic, b: Dyadic) -> Dyadic:
    if a.special == "nan" or b.special == "nan":
        return NAN
    if a.special == "inf" or b.special == "inf":
        if a.coefficient == 0 or b.coefficient == 0:
            return NAN
        return Dyadic(-1 if (a.coefficient < 0) != (b.coefficient < 0) else 1,
                      special="inf")
    return finite(a.coefficient * b.coefficient, a.exponent + b.exponent)


def exact_sum(values: Iterable[Dyadic]) -> Dyadic:
    terms = list(values)
    if any(x.special == "nan" for x in terms):
        return NAN
    infinities = {x.coefficient for x in terms if x.special == "inf"}
    if len(infinities) == 2:
        return NAN
    if infinities:
        return Dyadic(infinities.pop(), special="inf")
    terms = [x for x in terms if x.coefficient]
    if not terms:
        return ZERO
    exponent = min(x.exponent for x in terms)
    return finite(sum(x.coefficient << (x.exponent - exponent) for x in terms), exponent)


def round_fp32(value: Dyadic) -> int:
    """Exactly round to binary32, nearest with ties to even (including overflow)."""
    if value.special == "nan":
        return CANONICAL_NAN
    sign = int(value.coefficient < 0) << 31
    if value.special == "inf":
        return sign | 0x7F800000
    magnitude = abs(value.coefficient)
    if not magnitude:
        return 0
    exponent = magnitude.bit_length() - 1 + value.exponent
    if exponent > 127:
        return sign | 0x7F800000
    quantum = max(exponent - 23, -149)
    shift = quantum - value.exponent
    if shift > 0:
        integer, remainder = divmod(magnitude, 1 << shift)
        half = 1 << (shift - 1)
        integer += int(remainder > half or (remainder == half and integer & 1))
    else:
        integer = magnitude << -shift
    if quantum == -149 and integer < (1 << 23):
        return sign | integer
    if integer >= (1 << 24):
        integer >>= 1
        exponent += 1
    if exponent > 127:
        return sign | 0x7F800000
    return sign | ((max(-126, exponent) + 127) << 23) | (integer - (1 << 23))


@dataclass(frozen=True)
class Format:
    dtype: int
    bits: int
    exp_bits: int
    frac_bits: int
    bias: int
    scale_kind: str = "none"
    block: int = 1
    specials: str = "ieee"


FORMATS = {
    "fp16": Format(8, 16, 5, 10, 15),
    "bf16": Format(7, 16, 8, 7, 127),
    "mxfp8_e4m3": Format(5, 8, 4, 3, 7, "e8m0", 32, "nan_only"),
    "mxfp8_e5m2": Format(6, 8, 5, 2, 15, "e8m0", 32),
    "mxfp6_e3m2": Format(4, 6, 3, 2, 3, "e8m0", 32, "finite"),
    "mxfp6_e2m3": Format(3, 6, 2, 3, 1, "e8m0", 32, "finite"),
    "mxfp4_e2m1": Format(1, 4, 2, 1, 1, "e8m0", 32, "finite"),
    "nvfp4": Format(0, 4, 2, 1, 1, "ue4m3", 16, "finite"),
    "hif4": Format(2, 4, 0, 2, 0, "e6m2", 64, "finite"),
}
SCALE_TYPES = {"none": 2, "ue4m3": 1, "e8m0": 2, "e6m2": 3}
FP32 = Format(12, 32, 8, 23, 127)


def decode_binary(fmt: Format, raw: int) -> Dyadic:
    if type(raw) is not int or not 0 <= raw < (1 << fmt.bits):
        raise ValueError("Element exceeds its encoding width")
    sign = -1 if raw >> (fmt.bits - 1) else 1
    exponent = (raw >> fmt.frac_bits) & ((1 << fmt.exp_bits) - 1)
    fraction = raw & ((1 << fmt.frac_bits) - 1)
    if fmt.specials == "ieee" and exponent == (1 << fmt.exp_bits) - 1:
        return NAN if fraction else Dyadic(sign, special="inf")
    if fmt.specials == "nan_only" and (raw & ((1 << (fmt.bits - 1)) - 1)) == (1 << (fmt.bits - 1)) - 1:
        return NAN
    significand = fraction if exponent == 0 else (1 << fmt.frac_bits) + fraction
    return finite(sign * significand, max(1, exponent) - fmt.bias - fmt.frac_bits)


def decode_element(name: str, raw: int, group0: int = 0, group1: int = 0) -> Dyadic:
    fmt = FORMATS[name]
    if name != "hif4":
        return decode_binary(fmt, raw)
    if not 0 <= raw < 16 or group0 not in (0, 1) or group1 not in (0, 1):
        raise ValueError("Invalid HiF4 S1P2/group encoding")
    return finite((-1 if raw & 8 else 1) * (raw & 7), group0 + group1 - 2)


def decode_scale(kind: str, raw: int) -> Dyadic:
    if not 0 <= raw < 256:
        raise ValueError("Scale exceeds 8 bits")
    if kind == "e8m0":
        return NAN if raw == 255 else finite(1, raw - 127)
    if kind == "e6m2":
        # HiFloat4 v2: no zero/subnormal/Inf scale. 0x00 is 2^-48.
        return NAN if raw == 255 else finite(4 + (raw & 3), (raw >> 2) - 50)
    if kind == "ue4m3":
        if raw >= 128:
            raise ValueError("NVFP4 block scales are unsigned")
        return decode_binary(FORMATS["mxfp8_e4m3"], raw)
    raise ValueError(f"Unknown block scale: {kind}")


@dataclass
class Operand:
    codes: list[int]
    scales: list[int]
    group0: list[int]
    group1: list[int]


def shape(name: str, k: int) -> tuple[int, int, int]:
    if type(k) is not int or k <= 0:
        raise ValueError("K must be a positive integer")
    fmt = FORMATS[name]
    multiple = 8 if name == "hif4" else fmt.block
    if k % multiple:
        raise ValueError(f"{name}: K must be a multiple of {multiple}")
    return ((k + fmt.block - 1) // fmt.block if fmt.scale_kind != "none" else 0,
            k // 4 if name == "hif4" else 0, k // 8 if name == "hif4" else 0)


def dequantize(name: str, operand: Operand) -> list[Dyadic]:
    fmt = FORMATS[name]
    if (len(operand.scales), len(operand.group0), len(operand.group1)) != shape(name, len(operand.codes)):
        raise ValueError("Operand scale/group counts disagree with logical K")
    scales = [decode_scale(fmt.scale_kind, raw) for raw in operand.scales]
    result = []
    for i, raw in enumerate(operand.codes):
        value = decode_element(name, raw, operand.group0[i // 4] if operand.group0 else 0,
                               operand.group1[i // 8] if operand.group1 else 0)
        result.append(multiply(value, scales[i // fmt.block] if scales else ONE))
    return result


def dot_product(name: str, a: Operand, b: Operand) -> Dyadic:
    if len(a.codes) != len(b.codes):
        raise ValueError("A/B logical K mismatch")
    return exact_sum(multiply(x, y) for x, y in zip(dequantize(name, a), dequantize(name, b)))


def golden_fp32(name: str, a: Operand, b: Operand, c: int) -> int:
    return round_fp32(exact_sum((dot_product(name, a, b), decode_binary(FP32, c))))


def serialize(value: Dyadic) -> dict:
    return dict(coefficient=str(value.coefficient), exponent=value.exponent, special=value.special)


def deserialize(item: dict) -> Dyadic:
    if (set(item) != {"coefficient", "exponent", "special"}
            or type(item["coefficient"]) is not str or type(item["exponent"]) is not int
            or item["special"] not in ("", "nan", "inf")):
        raise ValueError("Invalid exact reference record")
    coefficient = int(item["coefficient"])
    if item["special"]:
        if item["exponent"] != 0 or coefficient not in ((0,) if item["special"] == "nan" else (-1, 1)):
            raise ValueError("Invalid exact special value")
        return Dyadic(coefficient, special=item["special"])
    value = finite(coefficient, item["exponent"])
    if serialize(value) != item:
        raise ValueError("Noncanonical exact finite reference")
    return value


def fp32_class(raw: int) -> str:
    exponent, fraction = (raw >> 23) & 255, raw & 0x7FFFFF
    if exponent == 255:
        return "nan" if fraction else "negative_inf" if raw >> 31 else "positive_inf"
    if exponent == 0:
        return "subnormal" if fraction else "negative_zero" if raw >> 31 else "positive_zero"
    return "normal"
