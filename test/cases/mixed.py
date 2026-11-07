"""Native mixed-profile corpus and inactive-port poison stimulus."""
import json
from adapters.cmodel import ROOT, read_inputs
from adapters.logical import read_logical_inputs
from reference.exact import DTYPES

PROFILES = ('t8h16q32e96', 't8h16q32e128', 't8h16q64e128')


def extended(profile, datatype):
    return 7 <= datatype <= 9 or (profile == PROFILES[2] and 3 <= datatype <= 6)


def corpus(profile):
    """Return each precision's native data plus its independent math golden."""
    for mode, datatype in DTYPES.items():
        if extended(profile, datatype):
            logical_k = (96 if profile == PROFILES[0] else 128) if datatype >= 7 else 64
            directory = next((ROOT / 'test/data/dp' / mode / f'K{logical_k}').glob('petile_*_961'))
            _, requests = read_logical_inputs(directory)
        else:
            directory = next((ROOT / 'test/data/dp' / mode).glob('*/*/inputs.txt')).parent
            _, requests = read_inputs(directory / 'inputs.txt')
        expected = [json.loads(line) for line in (directory / 'expected.jsonl').read_text().splitlines()]
        yield mode, requests, expected


def poison_inactive(request, profile):
    """Unused high ports carry ones, including NaN scale and HiF metadata."""
    result = dict(request)
    groups = 6 if profile == PROFILES[0] else 8
    for field, bits in [('a',64),('b',64),('a_scale',8),('b_scale',8),
                        ('a_e1',4),('b_e1',4),('a_e2',2),('b_e2',2)]:
        result[field] = format(int(request[field],16) | (((1 << (bits*(groups-4)))-1) << (bits*4)), 'x')
    return result
