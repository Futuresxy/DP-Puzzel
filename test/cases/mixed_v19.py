"""Deterministic v1.9 native-width vectors shared by CModel and RTL campaigns."""
import random

from cases.common import make, random_request
from cases.mixed import extended, poison_inactive
from reference.exact import DTYPES, FORMATS


def native_k(profile, datatype):
    if profile in ('qe', 'q32e64') or not extended(profile, datatype):
        return 16
    return 24 if profile == 't8h16q32e96' else 32


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
