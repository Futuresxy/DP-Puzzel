"""Fixed four-group profiles: numerical aliases, five-source coordinates, rejection."""
from pathlib import Path
import random
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import evaluate
from cases.common import random_request, make
from reference.exact import DTYPES

class LowpFrontend(unittest.TestCase):
    def test_profiles_and_five_source_sum(self):
        for profile, oracle, minimum in [('e64','e',7),('q32e64','qe',3)]:
            rng=random.Random(20271105)
            requests=[random_request(mode,rng,16,index) for index in range(32)
                      for mode,datatype in DTYPES.items() if minimum<=datatype<=9]
            for local,glob in [(27,40),(28,40),(32,64)]:
                cfg=dict(local_shift_mag_width=local,global_signed_align_width=glob)
                got=evaluate(requests,config=cfg|{'frontend':profile},trace=True)
                self.assertEqual(got,evaluate(requests,config=cfg|{'frontend':oracle},trace=True))
                if oracle=='qe': self.assertEqual(got,evaluate(requests,config=cfg,trace=True))
                for result in got:
                    self.assertEqual(len(result['trace'][4]['data']['groups']),4)
                    aligned=list(map(int,result['trace'][5]['data']['aligned_tc']))
                    self.assertEqual(len(aligned),5)
                    self.assertEqual(sum(aligned),int(result['trace'][6]['data']['sop_tc']))
                    self.assertEqual(result['trace'][6]['data']['width'],glob+3)

    def test_unsupported_types(self):
        for profile,minimum in [('e64',7),('q32e64',3)]:
            requests=[make(mode) for mode,datatype in DTYPES.items() if not minimum<=datatype<=9]
            results=evaluate(requests,config={'frontend':profile},allow_errors=True)
            self.assertTrue(all('error' in result for result in results))

    def test_fixed_capacity(self):
        for profile in ('e64','q32e64'):
            for config in ({'k_fp16':8},{'post_scale_norm_extra_stage':1}):
                with self.assertRaises(RuntimeError):
                    evaluate([make('nvfp4')],config=config|{'frontend':profile})

if __name__=='__main__': unittest.main()
