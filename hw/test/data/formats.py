"""Finite-source RNE quantization and independent raw-bit decoding.

Software arithmetic is binary64. HiF4 implements the mathematical hierarchy,
not the intermediate BF16 reciprocal/multiply instructions in paper Algorithm 1.
"""
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
import math
import struct


@dataclass(frozen=True)
class Format:
    bits: int
    exp: int
    frac: int
    bias: int
    block: int = 1
    scale: str = "none"
    specials: str = "finite"


FORMATS = {
    "bf16": Format(16, 8, 7, 127, specials="ieee"),
    "fp16": Format(16, 5, 10, 15, specials="ieee"),
    "mxfp8_e4m3": Format(8, 4, 3, 7, 32, "e8m0", "nan_only"),
    "mxfp8_e5m2": Format(8, 5, 2, 15, 32, "e8m0", "ieee"),
    "mxfp6_e3m2": Format(6, 3, 2, 3, 32, "e8m0"),
    "mxfp6_e2m3": Format(6, 2, 3, 1, 32, "e8m0"),
    "mxfp4": Format(4, 2, 1, 1, 32, "e8m0"),
    "nvfp4": Format(4, 2, 1, 1, 16, "e4m3"),
    "hif4": Format(4, 0, 2, 0, 64, "e6m2"),
}
SEMANTICS = "finite_rne_saturate_fp64_direct_v1"


def decode(name, raw):
    f = FORMATS[name]
    if not 0 <= raw < 1 << f.bits:
        raise ValueError("Element exceeds format width")
    sign = -1.0 if raw >> (f.bits - 1) else 1.0
    if name == "hif4":
        return sign * (raw & 7) / 4
    exp = (raw >> f.frac) & ((1 << f.exp) - 1)
    frac = raw & ((1 << f.frac) - 1)
    if f.specials == "ieee" and exp == (1 << f.exp) - 1:
        return math.nan if frac else sign * math.inf
    if f.specials == "nan_only" and (raw & ((1 << (f.bits - 1)) - 1)) == (1 << (f.bits - 1)) - 1:
        return math.nan
    significand = frac if exp == 0 else (1 << f.frac) + frac
    return sign * math.ldexp(significand, max(exp, 1) - f.bias - f.frac)


def decode_scale(kind, raw):
    if not 0 <= raw <= 255:
        raise ValueError("Scale exceeds storage width")
    if kind == "e8m0":
        return math.nan if raw == 255 else math.ldexp(1.0, raw - 127)
    if kind == "e4m3":
        if raw >= 128:
            raise ValueError("NVFP4 scales must be nonnegative")
        return decode("mxfp8_e4m3", raw)
    if kind == "e6m2":
        return math.nan if raw == 255 else math.ldexp(4 + (raw & 3), (raw >> 2) - 50)
    raise ValueError("Unknown scale format")


@lru_cache(None)
def book(name):
    f = FORMATS[name]
    return tuple((decode(name, raw), raw) for raw in range(1 << (f.bits - 1))
                 if math.isfinite(decode(name, raw)))


@lru_cache(None)
def scale_book(kind):
    return tuple((decode_scale(kind, raw), raw) for raw in range(127 if kind == "e4m3" else 255))


@lru_cache(None)
def book_values(name):
    return tuple(value for value, _ in book(name))


def nearest(entries, value, values=None):
    index = bisect_left(values if values is not None else [v for v, _ in entries], value)
    choices = entries[max(0, index - 1):min(len(entries), index + 1)]
    return min(choices, key=lambda pair: (abs(pair[0] - value), pair[1] & 1, pair[1]))[1]


def encode(name, value):
    if not math.isfinite(value):
        raise ValueError("AI source quantizer accepts finite tensors only")
    f = FORMATS[name]
    sign = int(math.copysign(1.0, value) < 0)
    return nearest(book(name), abs(value), book_values(name)) | (sign << (f.bits - 1))


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def quantize_rows(values, name, global_scale=1.0):
    """Quantize entire original K rows BEFORE cropping/PE packing."""
    import numpy as np
    f = FORMATS[name]
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] % f.block or not np.isfinite(values).all():
        raise ValueError("Expected finite 2-D rows with complete quantization blocks")
    if not math.isfinite(global_scale) or global_scale <= 0:
        raise ValueError("Invalid global scale")
    codes = np.empty(values.shape, dtype=np.uint16)
    scales = None if f.scale == "none" else np.empty((len(values), values.shape[1] // f.block), dtype=np.uint8)
    g0 = np.zeros((len(values), values.shape[1] // 4), dtype=np.uint8) if name == "hif4" else None
    g1 = np.zeros((len(values), values.shape[1] // 8), dtype=np.uint8) if name == "hif4" else None
    for row, vector in enumerate(values):
        for start in range(0, len(vector), f.block):
            block = vector[start:start + f.block]
            peak = float(np.max(np.abs(block)))
            factor = 1.0
            if f.scale == "e8m0":
                max_exp = math.frexp(book(name)[-1][0])[1] - 1
                exponent = math.frexp(peak)[1] - 1 - max_exp if peak else 0
                raw = min(254, max(0, exponent + 127))
                factor = decode_scale(f.scale, raw)
            elif f.scale == "e4m3":
                raw = nearest(scale_book(f.scale), peak / (6 * global_scale)) if peak else 0
                factor = decode_scale(f.scale, raw) * global_scale
            elif f.scale == "e6m2":
                raw = nearest(scale_book(f.scale), peak / 7) if peak else 0xc0
                factor = decode_scale(f.scale, raw)
                for offset in range(0, 64, 8):
                    g1[row, (start + offset) // 8] = int(np.max(np.abs(block[offset:offset + 8])) / factor >= 4)
                for offset in range(0, 64, 4):
                    parent_bit = int(g1[row, (start + offset) // 8])
                    g0[row, (start + offset) // 4] = int(np.max(np.abs(block[offset:offset + 4])) / (factor * 2 ** parent_bit) >= 2)
            if scales is not None:
                scales[row, start // f.block] = raw
            for offset, value in enumerate(block):
                index = start + offset
                divisor = factor
                if name == "hif4":
                    divisor *= 2 ** (int(g0[row, index // 4]) + int(g1[row, index // 8]))
                # An underflowed NV scale represents a zero block; preserve sign.
                scaled = float(value) / divisor if divisor else math.copysign(0.0, float(value))
                codes[row, index] = encode(name, scaled)
    return dict(codes=codes, scales=scales, g0=g0, g1=g1, global_scale=global_scale)


def dequantize(codes, name, scales=None, g0=None, g1=None, global_scale=1.0):
    import numpy as np
    f = FORMATS[name]
    result = np.empty(codes.shape, dtype=np.float64)
    for row in range(len(codes)):
        for index in range(codes.shape[1]):
            value = decode(name, int(codes[row, index]))
            if f.scale != "none":
                value *= decode_scale(f.scale, int(scales[row, index // f.block]))
            if name == "hif4":
                value *= 2 ** (int(g0[row, index // 4]) + int(g1[row, index // 8]))
            result[row, index] = value * global_scale
    return result
