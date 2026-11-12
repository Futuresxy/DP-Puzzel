"""Deterministic v1.9 native-width vectors shared by CModel and RTL campaigns."""
import random

from cases.common import make, random_request
from cases.mixed import extended, poison_inactive, groups_for_profile
from reference.exact import DTYPES, FORMATS


def native_k(profile, datatype):
    if profile in ('qe', 'q32e64') or not extended(profile, datatype):
        return 16
    return 4 * groups_for_profile(profile)


def directed(profile, random_per_mode=12):
    """Exercise active masking, scale classes, e2, cancellation and C corners."""
    rng = random.Random(0x190911)
    requests = []
    for mode, datatype in DTYPES.items():
        if profile in ('qe', 'q32e64') and not 3 <= datatype <= 9:
            continue
        k = native_k(profile, datatype)
        count = k // 4 * FORMATS[datatype][5]
        for c_bits in (0, 0x80000000, 1, 0x007fffff, 0x80000001,
                       0x7f800000, 0xff800000, 0x7fc00000, 0x7f800001):
            requests.append(make(mode, k, a=[0] * count, c=c_bits))
        requests.extend(random_request(mode, rng, k) for _ in range(random_per_mode))
        if 7 <= datatype <= 9:
            for scale_code in ((0, 1, 126, 127, 254, 255) if datatype == 7 else
                               (0, 1, 7, 8, 119, 127) if datatype == 8 else
                               (0, 1, 191, 192, 254, 255)):
                grain = 16 if datatype == 8 else 64 if datatype == 9 else 32
                scale_count = (count + grain - 1) // grain
                requests.append(make(mode, k, sa=[scale_code] * scale_count,
                                     sb=[scale_code] * scale_count))
            for signs in ([8] * count, [15, 7] * (count // 2),
                          [15] * (count // 2) + [7] * (count // 2)):
                requests.append(make(mode, k, a=signs, b=[7] * count, c=0x80000000))
        if datatype == 9:
            for left_shift in range(3):
                for right_shift in range(3):
                    lane_shifts = [left_shift, right_shift] * (count // 16)
                    metadata = ([1] * (count // 4), [1] * (count // 4),
                                [int(shift > 0) for shift in lane_shifts],
                                [int(shift == 2) for shift in lane_shifts])
                    requests.append(make(mode, k, a=[7] * count, b=[7] * count,
                                         metadata=metadata))
    if profile in ('t8h16q32e192', 't8h16q32e256', 't8h16q96e192', 't8h16q128e256'):
        # Every physical group must survive the 8/12-extension compression tree.
        # Nonuniform scales exercise every MX32/NV16/HiF64 broadcast boundary.
        groups = groups_for_profile(profile)
        for mode in ('mxfp4_e2m1', 'nvfp4', 'hif4'):
            datatype = DTYPES[mode]
            grain = 16 if datatype == 8 else 64 if datatype == 9 else 32
            count = groups * 16
            base_scale = 56 if datatype == 8 else 124 if datatype == 9 else 126
            scales = [base_scale + block % 3 for block in range(count // grain)]
            for group_index in range(groups):
                values = [0] * count
                values[group_index * 16:(group_index + 1) * 16] = [7] * 16
                requests.append(make(mode, groups * 4, a=values, b=[7] * count,
                                     sa=scales, sb=list(reversed(scales)), c=0x3f800000))
            # Uniform signs hit the largest finite sum; half/alternating signs
            # hit cancellation across (rather than only inside) four-leaf blocks.
            for signs in ([7] * count, [15] * count,
                          [7] * (count // 2) + [15] * (count // 2),
                          [7 if group % 2 else 15 for group in range(groups) for _ in range(16)]):
                requests.append(make(mode, groups * 4, a=signs, b=[7] * count,
                                     sa=scales, sb=scales, c=0x80000000))
    if profile in ('t8h16q96e192', 't8h16q128e256'):
        # One nonzero group moves across all 12/16 physical inputs, including
        # each Q32 scale block and each four-leaf CSA compression boundary.
        groups = groups_for_profile(profile)
        count = groups * 8
        for mode in ('mxfp8_e4m3', 'mxfp8_e5m2', 'mxfp6_e3m2', 'mxfp6_e2m3'):
            datatype = DTYPES[mode]
            _, exponent_bits, fraction_bits, bias, _, _ = FORMATS[datatype]
            one = bias << fraction_bits
            negative_one = one | (1 << (exponent_bits + fraction_bits))
            scales = [126 + block % 3 for block in range(groups // 4)]
            for group_index in range(groups):
                values = [0] * count
                values[group_index * 8:(group_index + 1) * 8] = [one] * 8
                requests.append(make(mode, groups * 4, a=values, b=[one] * count,
                                     sa=scales, sb=list(reversed(scales)), c=0x3f800000))
            for values in ([one] * count, [negative_one] * count,
                           [one] * (count // 2) + [negative_one] * (count // 2),
                           [one if group % 2 else negative_one for group in range(groups) for _ in range(8)]):
                requests.append(make(mode, groups * 4, a=values, b=[one] * count,
                                     sa=scales, sb=scales, c=0x80000000))
            # NaN-scale poisoning must propagate from every active Q32 block.
            for block_index in range(groups // 4):
                poison_scales = [127] * (groups // 4)
                poison_scales[block_index] = 255
                requests.append(make(mode, groups * 4, sa=poison_scales))
        # Alternate Q/E/high precision while all physical groups contain data;
        # the existing cycle runner shuffles these along with poisoned inactive
        # high-precision ports to exercise MAX qualification and valid bubbles.
        for group_index in range(groups):
            for mode in ('mxfp8_e4m3', 'mxfp4_e2m1'):
                elements = 8 if mode == 'mxfp8_e4m3' else 16
                one = 0x38 if elements == 8 else 2
                values = [0] * (groups * elements)
                values[group_index * elements:(group_index + 1) * elements] = [one] * elements
                requests.append(make(mode, groups * 4, a=values, b=[one] * len(values)))
    if profile == 't8h16q64e64':
        # Token-level special semantics: a NaN scale has a zero numerical
        # placeholder, so +/-Inf sets invalid and suppresses both Inf flags.
        for infinity_code in (0x7c, 0xfc):
            for scale_a, scale_b in (([127, 255], [127, 127]),
                                     ([127, 127], [127, 255]),
                                     ([127, 255], [127, 255])):
                requests.append(make('mxfp8_e5m2', 32,
                                     a=[0] * 32 + [infinity_code] * 32,
                                     b=[0x3c] * 64, sa=scale_a, sb=scale_b))
    if profile not in ('qe', 'q32e64'):
        requests = [poison_inactive(request, profile) if not extended(profile, request['a_datatype'])
                    else request for request in requests]
    for index, request in enumerate(requests):
        request['id'] = index
        request['last'] = index % 7 == 0
    return requests
