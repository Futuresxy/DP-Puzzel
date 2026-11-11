"""New TF32/INT8 precision modes and mixed floating/integer stream checks."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import evaluate, invoke, DEFAULT_CONFIG
from cases.common import make, random_request
from reference.architecture import reference


class ExtensionModel(unittest.TestCase):
    def test_integer_extremes_parameters_and_wrapping(self):
        rng=random.Random(808)
        for k in (4,8,16):
            n=k*2; requests=[random_request('int8',rng,k,i) for i in range(256)]
            requests += [make('int8',k,a=[a]*n,b=[b]*n,c=c) for a,b in ((128,128),(128,127),(127,127)) for c in (0x7fffffff,0x80000000)]
            results=evaluate(requests,config=dict(k_fp16=k))
            for req,res in zip(requests,results):
                ref=reference(req,DEFAULT_CONFIG|dict(k_fp16=k))
                self.assertEqual(int(res['d'],16),ref['bits'])
                self.assertEqual(res['flags']['integer_overflow'],not -(1<<31)<=ref['value'].value<(1<<31))
                self.assertFalse(any(v for f,v in res['flags'].items() if f!='integer_overflow'))

    def test_tf32_decomposition_and_padding(self):
        rng=random.Random(32)
        requests=[random_request('tf32',rng,ident=i) for i in range(256)]
        results=evaluate(requests,trace=True)
        for req,res in zip(requests,results):
            self.assertEqual(int(res['d'],16),reference(req,DEFAULT_CONFIG,True)['bits'])
            s1=res['trace'][0]['data']; s2=res['trace'][1]['data']
            for a,b,p in zip(s1['a'],s1['b'],s2['products']):
                self.assertEqual(int(a['m'])*int(b['m']),int(p['m']))
                self.assertLess(int(a['m']),1<<11)
        bad=make('tf32'); bad['a']=format(int(bad['a'],16)|1,'x')
        self.assertIn('error',evaluate([bad],allow_errors=True)[0])

    def test_mixed_result_types_same_latency(self):
        modes=['tf32','int8','fp16','int8','hif4','bf16','int8']
        requests=[make(m,ident=i,last=i in (1,4,6)) for i,m in enumerate(modes)]
        commands=[dict(op='step',request=r,a_valid=True,b_valid=True,c_valid=True) for r in requests]
        commands += [dict(op='step')]*8
        results=invoke(commands)
        self.assertTrue(all(not t['valid'] for t in results[:8]))
        for r,t in zip(requests,results[8:]):
            self.assertEqual(t['result']['id'],r['id'])
            self.assertEqual(t['result']['d_datatype'],r['c_datatype'])
            self.assertEqual(t['result']['last'],r['last'])
            self.assertEqual(int(t['result']['d'],16),reference(r,DEFAULT_CONFIG,True)['bits'])


if __name__=='__main__': unittest.main()
