"""v1.8 directed numerical contract; legacy mode is only a comparison oracle."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import DEFAULT_CONFIG, evaluate
from cases.common import make, random_request
from reference.architecture import reference


class BaselineV18(unittest.TestCase):
    def test_hif4_lane_e2_and_cancellation(self):
        requests = []
        for left_shift in range(3):
            for right_shift in range(3):
                for negative in (False, True):
                    metadata = ([1]*4, [1]*4,
                                [int(left_shift > 0), int(right_shift > 0)],
                                [int(left_shift == 2), int(right_shift == 2)])
                    requests.append(make('hif4', 4, a=[7]*8 + [15 if negative else 7]*8,
                                         b=[7]*16, metadata=metadata, ident=len(requests)))
        cfg = DEFAULT_CONFIG | dict(k_fp16=4)
        current = evaluate(requests, config=cfg, trace=True)
        previous = evaluate(requests, config=cfg | dict(legacy_multi=True))
        for request, result, old in zip(requests, current, previous):
            self.assertEqual(result['d'], old['d'])
            self.assertEqual(int(result['d'], 16), reference(request, cfg)['bits'])
            self.assertEqual(result['trace'][1]['data']['r'], [0])
            self.assertTrue(all(delta == 0 for lane in result['trace'][2]['data']['delta'] for delta in lane))
            token = result['trace'][4]['data']['groups'][0]
            self.assertEqual(token['f'], 19)
            self.assertEqual(token['compare_exp'], token['anchor_raw'] - token['z'])

    def test_no_c_lzd_and_no_flush_to_zero(self):
        requests = [make('bf16', 4, a=[0]*4, c=bits, ident=index)
                    for index, bits in enumerate((1, 0x007fffff, 0x80000001, 0x00800000))]
        cfg = DEFAULT_CONFIG | dict(k_fp16=4)
        for request, result in zip(requests, evaluate(requests, config=cfg, trace=True)):
            self.assertEqual(int(result['d'], 16), int(request['c'], 16))
            token = result['trace'][4]['data']['c']
            self.assertEqual(token['z'], 0)
            self.assertEqual(token['compare_exp'], -126)
        # A tiny nonzero group plus C: independently quantize at C's -126 upper bound.
        requests = [make('bf16', 4, a=[1, 0, 0, 0], b=[1]*4, c=bits, ident=index)
                    for index, bits in enumerate((1, 0x80000001, 0x007fffff))]
        for request, result in zip(requests, evaluate(requests, config=cfg)):
            self.assertEqual(int(result['d'], 16), reference(request, cfg, True)['bits'])

    def test_inactive_c_anchor_placeholder(self):
        requests = [make('bf16', 4, c=bits, ident=index)
                    for index,bits in enumerate((0,0x80000000,0x7fc00000,0x7f800000,0xff800000))]
        for result in evaluate(requests,config=dict(k_fp16=4),trace=True):
            token=result['trace'][4]['data']['c']
            self.assertEqual((token['anchor_raw'],token['compare_exp'],token['z']),(0,0,0))

    def test_scale_signed_exponents_and_legacy_final_equivalence(self):
        rng = random.Random(1809)
        for width in (27, 28, 32):
            requests = [random_request(mode, rng, 4, index)
                        for index, mode in enumerate(['mxfp4_e2m1', 'nvfp4', 'hif4']*80)]
            cfg = DEFAULT_CONFIG | dict(k_fp16=4, local_shift_mag_width=width)
            current = evaluate(requests, config=cfg, trace=True)
            previous = evaluate(requests, config=cfg | dict(legacy_multi=True))
            for request, result, old in zip(requests, current, previous):
                self.assertEqual(result['d'], old['d'])
                self.assertEqual(int(result['d'], 16), reference(request, cfg, True)['bits'])
                scales = result['trace'][0]['data']['scale_a'] + result['trace'][0]['data']['scale_b']
                self.assertTrue(all(-127 <= scale['e'] <= 127 for scale in scales))


if __name__ == '__main__':
    unittest.main()
