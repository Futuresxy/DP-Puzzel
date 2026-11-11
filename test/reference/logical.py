"""Exact Q/E dot+C reference whose dimension is logical K, not hardware K_FP16.

Uses the independent external-format/Fraction primitives from exact.py. There
is no finite-window truncation, hardware pipeline or CModel call in this module.
"""
from fractions import Fraction

from reference.exact import FORMATS, binary, finite, fp32, multiply, power, scale, sum_values

Q_TYPES = (3, 4, 5, 6)
E_TYPES = (7, 8, 9)


def exact_logical(request, logical_k):
    """Evaluate packed logical operands with one explicit scale byte per group.

    Q groups contain 8 elements and E groups 16. Those boundaries only select
    the supplied scale; all arithmetic remains exact before final FP32 RNE.
    """
    datatype = request['a_datatype']
    if datatype not in Q_TYPES + E_TYPES or request['b_datatype'] != datatype:
        raise ValueError('logical reference requires same-format Q/E operands')
    if request['c_datatype'] != 0:
        raise ValueError('logical Q/E reference requires FP32 C')
    _, exponent_bits, fraction_bits, bias, storage_bits, group_elements = FORMATS[datatype]
    if logical_k <= 0 or logical_k % group_elements:
        raise ValueError('logical K must contain complete Q8/E16 groups')
    sides = []
    for side in ('a', 'b'):
        packed = int(request[side], 16)
        e1 = int(request[f'{side}_e1'], 16)
        e2 = int(request[f'{side}_e2'], 16)
        values = []
        for index in range(logical_k):
            raw = (packed >> (index * storage_bits)) & ((1 << storage_bits) - 1)
            if datatype == 9:
                magnitude = Fraction(raw & 7, 4) * power((e1 >> (index // 4) & 1) +
                                                        (e2 >> (index // 8) & 1))
                values.append(finite(-magnitude if raw & 8 else magnitude, bool(raw & 8)))
            else:
                if datatype in (5, 6):
                    raw >>= 2
                values.append(binary(raw, exponent_bits, fraction_bits, bias,
                                     ieee=datatype == 4, e4m3=datatype == 3)[0])
        sides.append(values)
    groups = []
    for group_index in range(logical_k // group_elements):
        first = group_index * group_elements
        products = [multiply(sides[0][index], sides[1][index])
                    for index in range(first, first + group_elements)]
        scales = []
        for side in ('a', 'b'):
            raw = int(request[f'{side}_scale'], 16) >> (group_index * 8) & 255
            kind = request[f'{side}_scale_datatype']
            # NVFP4 scale E4M3 is an unsigned magnitude; bit 7 is not a sign.
            scales.append(scale(raw & 127 if kind == 2 else raw, kind))
        groups.append(multiply(sum_values(products), multiply(*scales)))
    c_value = binary(int(request['c'], 16), 8, 23, 127)[0]
    value = sum_values(groups + [c_value])
    return dict(bits=fp32(value), value=value)


def serialize_exact(result):
    """Store the exact rational value as decimal strings, without a float step."""
    value = result['value']
    return dict(kind=value.kind, negative=value.negative, invalid=value.invalid,
                numerator=str(value.value.numerator) if value.kind == 'finite' else None,
                denominator=str(value.value.denominator) if value.kind == 'finite' else None)
