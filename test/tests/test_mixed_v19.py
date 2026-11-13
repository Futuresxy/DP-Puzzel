"""v1.9 native frontends, narrow coordinates, carry-save and cycle contracts."""
from itertools import product
import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import DEFAULT_CONFIG, ROOT, evaluate, invoke, read_inputs
from cases.common import make, random_request
from cases.mixed import PROFILES, corpus, extended
from cases.mixed_v19 import directed
from reference.architecture import reference
from reference.exact import DTYPES, ulp_distance

RUN = ROOT / 'test/runs/cmodel/v19_validation'


def model(requests, config, **kwargs):
    return evaluate(requests, config=DEFAULT_CONFIG | config | {'architecture_v19': True},
                    run_dir=RUN, **kwargs)


class MixedV19(unittest.TestCase):
    def test_directed_independent_reference_and_csa(self):
        for profile in (*PROFILES, 'q32e64'):
            requests = directed(profile)
            cfg = DEFAULT_CONFIG | dict(frontend=profile, architecture_v19=True)
            for request, result in zip(requests, model(requests, cfg, trace=True)):
                expected = reference(request, cfg, True)
                self.assertEqual(int(result['d'], 16), expected['bits'], (profile, request['id']))
                stages = [entry['data'] for entry in result['trace']]
                c_token = stages[4]['c']
                self.assertEqual(c_token['z'], 0)
                self.assertEqual(c_token['compare_exp'], c_token['anchor_raw'])
                rows = stages[6]['carry_save']
                width = rows['width']
                residue = (int(rows['sum_row']) + int(rows['carry_row'])) % (1 << width)
                signed = residue - (1 << width) if residue >> (width - 1) else residue
                self.assertEqual(signed, int(stages[6]['sop_tc']))
                self.assertEqual(signed, sum(map(int, stages[5]['aligned_tc'])))
                if profile != 'q32e64' and not extended(profile, request['a_datatype']):
                    self.assertFalse(rows['extension_active'])
                    self.assertTrue(all(int(value) == 0 for value in stages[5]['aligned_tc'][4:-1]))

    def test_e_stage_coordinates_and_narrow_lzd(self):
        rng = random.Random(0xE1909)
        for k in (4, 8, 16):
            requests = [random_request(mode, rng, k, index)
                        for index in range(32) for mode in ('mxfp4_e2m1', 'nvfp4', 'hif4')]
            for local, global_width in ((27, 40), (28, 40), (32, 64)):
                cfg = dict(k_fp16=k, local_shift_mag_width=local,
                           global_signed_align_width=global_width)
                dedicated = model(requests, cfg | {'frontend': 'e'}, trace=True)
                shared = model(requests, cfg | {'frontend': 'multi'}, trace=True)
                for result, baseline in zip(dedicated, shared):
                    self.assertEqual(result['d'], baseline['d'])
                    stages = [entry['data'] for entry in result['trace']]
                    self.assertEqual((stages[2]['width'], stages[2]['f']), (14, 4))
                    self.assertEqual(stages[2]['sop_tc'],
                                     [value for group in stages[3]['lane_fused_tc'] for value in group])
                    self.assertEqual(stages[4]['groups'], baseline['trace'][4]['data']['groups'])
                    narrow = [entry for entry in stages[4]['scale_multiplier'] if 'lzd_width' in entry]
                    self.assertEqual(len(narrow), k // 4)
                    for token, entry in zip(stages[4]['groups'], narrow):
                        magnitude = int(entry['lzd_magnitude'])
                        self.assertEqual(int(token['m']), magnitude << (local + 3 - 22))
                        # The project LZD returns active=0/count=0 for zero.
                        self.assertEqual(entry['leading_zero_count'],
                                         22 - magnitude.bit_length() if magnitude else 0)
                        if not token['zero'] and not any(token['special'].values()):
                            self.assertEqual(token['z'], entry['leading_zero_count'])
                            self.assertEqual(token['compare_exp'], entry['raw_anchor_s3'] - token['z'])

    def test_e_all_nibbles_and_metadata(self):
        requests = []
        for mode in ('mxfp4_e2m1', 'nvfp4', 'hif4'):
            metadata = product((0, 1), repeat=4) if mode == 'hif4' else [(0, 0, 0, 0)]
            for e1_a, e1_b, e2_a, e2_b in metadata:
                meta = ([e1_a] * 4, [e1_b] * 4, [e2_a] * 2, [e2_b] * 2) if mode == 'hif4' else None
                for operand_a, operand_b in product(range(16), repeat=2):
                    requests.append(make(mode, 4, a=[operand_a] + [0] * 15,
                                         b=[operand_b] + [0] * 15, metadata=meta,
                                         ident=len(requests)))
        cfg = DEFAULT_CONFIG | dict(frontend='e', k_fp16=4, architecture_v19=True)
        for request, result in zip(requests, model(requests, cfg)):
            self.assertEqual(int(result['d'], 16), reference(request, cfg)['bits'])

    def test_qe_and_mixed_parameter_windows(self):
        for k in (4, 8, 16):
            rng = random.Random(k + 1900)
            requests = [random_request(mode, rng, k, index) for index in range(12)
                        for mode, datatype in DTYPES.items() if 3 <= datatype <= 9]
            for local, global_width in ((27, 40), (28, 48), (32, 64)):
                cfg = dict(k_fp16=k, local_shift_mag_width=local,
                           global_signed_align_width=global_width)
                qe = model(requests, cfg | {'frontend': 'qe'})
                baseline = model(requests, cfg | {'frontend': 'multi'})
                self.assertEqual(qe, baseline)
        for profile in PROFILES:
            requests = directed(profile, random_per_mode=1)
            for local, global_width in ((27, 40), (32, 64)):
                cfg = DEFAULT_CONFIG | dict(frontend=profile, architecture_v19=True,
                                           local_shift_mag_width=local,
                                           global_signed_align_width=global_width)
                for request, result in zip(requests, model(requests, cfg)):
                    self.assertEqual(int(result['d'], 16), reference(request, cfg, True)['bits'])

    def test_native_corpus(self):
        summaries = {}
        for profile in (*PROFILES, 'q32e64'):
            if profile == 'q32e64':
                datasets = []
                for mode, datatype in DTYPES.items():
                    if not 3 <= datatype <= 9:
                        continue
                    directory = next((ROOT / 'test/data/dp' / mode).glob('*/correct_961'))
                    _, requests = read_inputs(directory / 'inputs.txt')
                    expected = [json.loads(line) for line in (directory / 'expected.jsonl').read_text().splitlines()]
                    datasets.append((mode, requests, expected))
            else:
                datasets = corpus(profile)
            summaries[profile] = {}
            cfg = DEFAULT_CONFIG | dict(frontend=profile, architecture_v19=True)
            for mode, requests, golden in datasets:
                exact_count = 0
                max_ulp = 0
                for request, result, expected in zip(requests, model(requests, cfg), golden):
                    finite_window = reference(request, cfg, True)
                    self.assertEqual(int(result['d'], 16), finite_window['bits'], (profile, mode, request['id']))
                    self.assertEqual((result['id'], result['last']), (request['id'], request['last']))
                    exact_bits = int(expected['exact_fp32_or_int32'], 16)
                    distance = ulp_distance(int(result['d'], 16), exact_bits)
                    exact_count += int(result['d'], 16) == exact_bits
                    if distance is None:
                        self.assertEqual(int(result['d'], 16), exact_bits)
                    else:
                        max_ulp = max(max_ulp, distance)
                self.assertLessEqual(max_ulp, 4)
                summaries[profile][mode] = dict(count=len(requests), exact=exact_count,
                                                 max_ulp=max_ulp, architecture_mismatches=0)
                print(f'v1.9 {profile}/{mode}: checked={len(requests)} exact={exact_count} max_ulp={max_ulp}', flush=True)
        (RUN / 'native_summary.json').write_text(json.dumps(summaries, indent=2) + '\n')

    def test_l8_stream_bubbles_reset(self):
        for profile in (*PROFILES, 'q32e64'):
            requests = directed(profile, random_per_mode=1)
            random.Random(1909).shuffle(requests)
            requests = requests[:48]
            values = model(requests, dict(frontend=profile))
            by_id = {result['id']: result for result in values}
            commands, expected, pending = [], [], {}
            for cycle in range(64):
                reset = cycle in (0, 19)
                if reset:
                    pending.clear()
                due = pending.pop(cycle, None)
                request = requests[cycle - 1] if 0 < cycle <= len(requests) else None
                accepted = request is not None and cycle % 7 != 0 and not reset
                if accepted:
                    pending[cycle + 8] = request['id']
                command = dict(op='step', reset=reset, a_valid=accepted,
                               b_valid=accepted, c_valid=accepted)
                if request:
                    command['request'] = request
                commands.append(command)
                expected.append((accepted, due))
            ticks = invoke(commands, config=dict(frontend=profile, architecture_v19=True), run_dir=RUN)
            for tick, (accepted, due) in zip(ticks, expected):
                self.assertEqual(tick['accepted'], accepted)
                self.assertEqual(tick['valid'], due is not None)
                if due is not None:
                    self.assertEqual(tick['result'], by_id[due])


if __name__ == '__main__':
    unittest.main()
