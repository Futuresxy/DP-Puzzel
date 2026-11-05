"""E frontend stage coordinates, shared backend, formats and cycle protocol."""
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import DEFAULT_CONFIG, ROOT, evaluate, invoke, read_inputs
from cases.common import make, random_request
from reference.exact import power, reference, scale, unpack

MODES = ('mxfp4_e2m1', 'nvfp4', 'hif4')


class EFrontend(unittest.TestCase):
    def test_shared_saved_vectors_and_backend(self):
        for mode in MODES:
            _, requests = read_inputs(ROOT / 'test/data/dp' / mode / 'K64/correct_961/inputs.txt')
            old = evaluate(requests, trace=True)
            new = evaluate(requests, config={'frontend': 'e'}, trace=True)
            for req, multi, e in zip(requests, old, new):
                self.assertEqual({k: v for k, v in multi.items() if k != 'trace'},
                                 {k: v for k, v in e.items() if k != 'trace'})
                # S6's aligned numbers/E_max and all of S7/S8 are identical.
                self.assertEqual(multi['trace'][5]['data']['aligned_tc'], e['trace'][5]['data']['aligned_tc'])
                self.assertEqual(multi['trace'][5]['data']['E_max'], e['trace'][5]['data']['E_max'])
                self.assertEqual(multi['trace'][6:], e['trace'][6:])
                self.assertEqual(e['trace'][1]['data']['pair_width'], 10)
                for g, (before, after) in enumerate(zip(multi['trace'][4]['data']['groups'],
                                                       e['trace'][4]['data']['groups'])):
                    if mode != 'hif4':
                        self.assertEqual(before, after)
                    else:
                        k = 2 - multi['trace'][1]['data']['r'][g]
                        self.assertEqual(int(before['m']), int(after['m']) << k)
                        self.assertEqual(before['f'], after['f'] + 2)
                        if not after['zero'] and not any(after['special'].values()):
                            self.assertEqual(after['anchor_raw'], before['anchor_raw'] + k)
                            self.assertEqual(after['z'], before['z'] + k)

    def test_independent_stage_values_and_parameter_windows(self):
        rng = random.Random(0xE642027)
        for k in (4, 8, 16):
            requests = [random_request(mode, rng, k, len(MODES)*i+j)
                        for i in range(24) for j, mode in enumerate(MODES)]
            for local, glob, extra in ((27, 40, 0), (28, 48, 1), (32, 64, 0)):
                cfg = DEFAULT_CONFIG | dict(k_fp16=k, local_shift_mag_width=local,
                                            global_signed_align_width=glob,
                                            post_scale_norm_extra_stage=extra)
                values = evaluate(requests, config=cfg | {'frontend': 'e'}, trace=True)
                for req, got in zip(requests, values):
                    self.assertEqual(int(got['d'], 16), reference(req, cfg, True)['bits'])
                    sides, _, _ = unpack(req, k)
                    a, b = sides
                    s2, s3, s4, s5 = (got['trace'][i]['data'] for i in range(1, 5))
                    raw_fraction = 4 if req['a_datatype'] == 9 else 2
                    for lane, pairs in enumerate(s2['pairs_tc']):
                        base = lane*8
                        p = a[base][1]+b[base][1] if req['a_datatype'] == 9 else 0
                        expected = []
                        for j in range(0, 8, 2):
                            pair = sum(a[i][0].value*b[i][0].value for i in (base+j, base+j+1))
                            pair *= power(raw_fraction-p)
                            self.assertEqual(pair.denominator, 1)
                            expected.append(int(pair))
                        self.assertEqual(list(map(int, pairs)), expected)
                        self.assertEqual(int(s3['sop_tc'][lane]), sum(expected))
                        self.assertEqual(s2['all_negative'][lane],
                                         all(a[i][0].negative != b[i][0].negative for i in range(base, base+8)))
                    for g, token in enumerate(s5['groups']):
                        exact_sum = sum(a[i][0].value*b[i][0].value for i in range(g*16, (g+1)*16))
                        self.assertEqual(Fraction(int(s4['sop_tc'][g]), 16), exact_sum)
                        self.assertLess(int(s4['magnitude'][g]), 1 << 14)
                        sa = scale(int(req['a_scale'], 16) >> (8*g) & 255, req['a_scale_datatype'])
                        sb = scale(int(req['b_scale'], 16) >> (8*g) & 255, req['b_scale_datatype'])
                        if sa.kind == sb.kind == 'finite':
                            value = (-1 if token['sign'] else 1)*int(token['m'])
                            value *= power(token['anchor_raw']-(token['width']-1))
                            self.assertEqual(value, exact_sum*sa.value*sb.value)
                        else:
                            self.assertTrue(token['special']['nan'])

    def test_all_element_codes_and_hif_metadata(self):
        # One product in an E16 group: all external nibble pairs and all e1/e2.
        requests = []
        for mode in MODES:
            metadata = list(product((0, 1), repeat=4)) if mode == 'hif4' else [(0, 0, 0, 0)]
            for e1a, e1b, e2a, e2b in metadata:
                meta = ([e1a]*4, [e1b]*4, [e2a]*2, [e2b]*2) if mode == 'hif4' else None
                for a, b in product(range(16), repeat=2):
                    requests.append(make(mode, 4, a=[a]+[0]*15, b=[b]+[0]*15,
                                         metadata=meta, ident=len(requests)))
        for req, got in zip(requests, evaluate(requests, config={'frontend': 'e', 'k_fp16': 4})):
            self.assertEqual(int(got['d'], 16), reference(req, DEFAULT_CONFIG | {'k_fp16': 4})['bits'])

    def test_extremes_cancellation_zero_and_scale_classes(self):
        nz = 0x80000000
        requests = [
            make('nvfp4', a=[15]*64, b=[7]*64, sa=[0x77]*4, sb=[0x77]*4),
            make('hif4', a=[15]*64, b=[7]*64,
                 metadata=([1]*16, [1]*16, [1]*8, [1]*8)),
            make('nvfp4', a=[15]*64, b=[7]*64, sa=[0]*4, c=nz),
            make('nvfp4', a=[8]*64, b=[7]*64, c=nz),
            make('nvfp4', a=([15]*8+[7]*8)*4, b=[7]*64, c=nz),
        ]
        for mode in MODES:
            for c in (0, nz, 1, 0x007fffff, 0x7f7fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0x7f800001):
                requests.append(make(mode, c=c))
            for code in range(128 if mode == 'nvfp4' else 256):
                count = 4 if mode == 'nvfp4' else 2 if mode == 'mxfp4_e2m1' else 1
                requests.append(make(mode, sa=[code]*count, sb=[code]*count))
        old = evaluate(requests)
        new = evaluate(requests, config={'frontend': 'e'}, trace=True)
        for req, before, after in zip(requests, old, new):
            self.assertEqual(before, {k: v for k, v in after.items() if k != 'trace'})
            self.assertEqual(int(after['d'], 16), reference(req, DEFAULT_CONFIG, True)['bits'])
        self.assertEqual(new[0]['trace'][1]['data']['pairs_tc'][0], ['-288']*4)
        self.assertEqual(new[1]['trace'][1]['data']['pairs_tc'][0], ['-392']*4)
        self.assertEqual(new[0]['trace'][3]['data']['magnitude'], ['9216']*4)
        self.assertEqual(new[1]['trace'][3]['data']['magnitude'], ['12544']*4)
        self.assertEqual([int(row['d'], 16) for row in new[2:5]], [nz, nz, 0])

    def test_cycle_stream_and_frontend_rejection(self):
        for k, extra in ((16, 0), (4, 1)):
            cfg = DEFAULT_CONFIG | dict(frontend='e', k_fp16=k, post_scale_norm_extra_stage=extra)
            latency = 8+extra
            commands, expected, pending = [], [], {}
            def push(req=None, valids=(False, False, False), reset=False, legal=True):
                cycle = len(commands)
                if reset:
                    pending.clear()
                out = pending.pop(cycle, None)
                accepted = all(valids) and legal and not reset
                if accepted:
                    pending[cycle+latency] = req
                item = dict(op='step', reset=reset, a_valid=valids[0], b_valid=valids[1], c_valid=valids[2])
                if req is not None:
                    item['request'] = req
                commands.append(item)
                expected.append((out, accepted))
            for i in range(36):
                if i == 8:
                    push(reset=True)
                if i == 15:
                    push(make('fp16', k, ident=999), (True, True, True), legal=False)
                if i % 7 == 0:
                    push()
                req = make(MODES[i % 3], k, ident=i, last=i % 5 == 0)
                push(req, (True, True, True))
            for _ in range(latency):
                push()
            ticks = invoke(commands, config=cfg, trace=True)
            for tick, (out, accepted) in zip(ticks, expected):
                self.assertEqual(tick['accepted'], accepted)
                self.assertEqual(tick['valid'], out is not None)
                if out:
                    self.assertEqual((tick['result']['id'], tick['result']['last']), (out['id'], out['last']))
                    self.assertEqual(int(tick['result']['d'], 16), reference(out, cfg, True)['bits'])
            self.assertTrue(any(t['protocol_error'] for t in ticks))
            first = next(i for i, tick in enumerate(ticks) if tick['accepted'])
            self.assertEqual(ticks[first+1]['registers_after_edge'][1]['cutpoint']['operation'], 'e_multiply_and_pairs')
            self.assertEqual(ticks[first+2]['registers_after_edge'][2]['cutpoint']['operation'], 'e_lane_sop_tree')
            self.assertEqual(ticks[first+3]['registers_after_edge'][3]['cutpoint']['operation'], 'e_group_sum_and_abs')

    def test_config_and_payload_rejection(self):
        profile = json.loads((ROOT / 'src/configs/dp/e64.json').read_text())
        cfg = invoke([dict(op='config')], config=profile)[0]
        self.assertEqual((cfg['frontend'], cfg['k_e'], cfg['pair_bits'], cfg['lane_bits']), ('e', 64, 10, 12))
        bad = [make(mode) for mode in ('tf32', 'fp16', 'bf16', 'mxfp8_e4m3', 'int8')]
        negative_scale = make('nvfp4')
        negative_scale['a_scale'] = '80808080'
        bad.append(negative_scale)
        self.assertTrue(all('error' in r for r in evaluate(bad, config={'frontend': 'e'}, allow_errors=True)))
        for frontend in ('e64', 'unknown', 1):
            with self.assertRaises(RuntimeError):
                invoke([dict(op='config')], config={'frontend': frontend})


if __name__ == '__main__':
    unittest.main()
