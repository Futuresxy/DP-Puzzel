"""E/QE192/E/QE256 native profiles: capacity, per-group contribution and exact CSA."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import DEFAULT_CONFIG, ROOT, evaluate, invoke
from cases.common import make
from cases.mixed_v19 import directed
from cases.mixed import extended
from reference.architecture import reference


class EExpansion(unittest.TestCase):
    def test_default_current_architecture_and_reject_legacy(self):
        for profile in ('t8h16q32e192', 't8h16q32e256', 't8h16q96e192', 't8h16q128e256'):
            request = make('fp16')
            result = evaluate([request], config=dict(frontend=profile))
            self.assertEqual(result, evaluate([request], config=dict(frontend=profile, architecture_v19=True)))
            for updates in (dict(architecture_v19=False), dict(k_fp16=8),
                            dict(post_scale_norm_extra_stage=1)):
                with self.assertRaises(RuntimeError):
                    evaluate([request], config=dict(frontend=profile) | updates)

    def test_native_width_cutpoints_and_independent_reference(self):
        for profile, groups in (('t8h16q32e192', 12), ('t8h16q32e256', 16),
                                ('t8h16q96e192', 12), ('t8h16q128e256', 16)):
            requests = directed(profile, random_per_mode=3)
            for local, global_width in ((27, 40), (28, 40), (32, 64)):
                cfg = DEFAULT_CONFIG | dict(frontend=profile, architecture_v19=True,
                                           local_shift_mag_width=local,
                                           global_signed_align_width=global_width)
                results = evaluate(requests, config=cfg, trace=True,
                                   run_dir=ROOT/'test/runs/cmodel/e_expansion')
                for request, result in zip(requests, results):
                    self.assertEqual(int(result['d'], 16), reference(request, cfg, True)['bits'],
                                     (profile, request['id'], local, global_width))
                    stages = [entry['data'] for entry in result['trace']]
                    self.assertEqual(len(stages[4]['groups']), groups)
                    self.assertEqual(len(stages[5]['aligned_tc']), groups + 1)
                    width = global_width + groups.bit_length()
                    self.assertEqual(stages[6]['width'], width)
                    rows = stages[6]['carry_save']
                    residue = (int(rows['sum_row']) + int(rows['carry_row'])) % (1 << width)
                    signed = residue - (1 << width) if residue >> (width - 1) else residue
                    self.assertEqual(signed, int(stages[6]['sop_tc']))
                    self.assertEqual(signed, sum(map(int, stages[5]['aligned_tc'])))
                    if not extended(profile, request['a_datatype']):
                        self.assertFalse(rows['extension_active'])
                        self.assertTrue(all(int(value) == 0 for value in stages[5]['aligned_tc'][4:-1]))


if __name__ == '__main__':
    unittest.main()
