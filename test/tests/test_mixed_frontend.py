"""Mixed DP numeric, stage-coordinate, participation and L8 protocol checks."""
import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import ROOT, DEFAULT_CONFIG, evaluate, invoke, read_inputs
from adapters.logical import read_logical_inputs
from cases.common import random_request, make
from reference.exact import DTYPES, ulp_distance, reference

from cases.mixed import PROFILES, extended, corpus, poison_inactive, qe_extension


class MixedFrontend(unittest.TestCase):
    def test_native_corpus_and_errors(self):
        summaries = {}
        for profile in PROFILES:
            summaries[profile] = {}
            for mode, requests, golden in corpus(profile):
                got = evaluate(requests, config={'frontend':profile})
                exact = 0
                maximum = 0
                above_four = []
                for req, result, expected in zip(requests, got, golden):
                    self.assertEqual(result['id'], req['id'])
                    self.assertEqual(result['last'], req['last'])
                    if not extended(profile, req['a_datatype']):
                        self.assertEqual(result['d'], expected['d'])
                    expected_bits = expected.get('exact_fp32_or_int32')
                    if expected_bits is None:
                        expected_bits = f"{reference(req, DEFAULT_CONFIG)['bits']:08x}"
                    bits = int(result['d'],16)
                    reference_bits = int(expected_bits,16)
                    distance = ulp_distance(bits, reference_bits)
                    exact += bits == reference_bits
                    if distance is None:
                        self.assertEqual(bits, reference_bits)
                    else:
                        maximum = max(maximum,distance)
                        if distance > 4:
                            above_four.append({'id':req['id'],'ulp':distance,'d':result['d'],
                                               'exact':expected_bits})
                self.assertLessEqual(maximum,4, f'{profile}/{mode} fixed corpus exceeds 4 ULP')
                summaries[profile][mode] = dict(count=len(requests), exact=exact,
                                                max_ulp=maximum, above_4=above_four)
                print(f'{profile} {mode}: {len(requests)} checked, exact={exact}, max_ulp={maximum}',flush=True)
        output = ROOT / 'test/runs/cmodel/mixed_summary.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summaries,indent=2)+'\n')

    def test_qe_matches_multi_cutpoints(self):
        rng=random.Random(0x716)
        requests=[random_request(mode,rng,4,index) for index in range(20)
                  for mode, datatype in DTYPES.items() if 3 <= datatype <= 9]
        multi=evaluate(requests,config={'k_fp16':4},trace=True)
        qe=evaluate(requests,config={'k_fp16':4,'frontend':'qe'},trace=True)
        self.assertEqual(multi,qe)
        rejected=evaluate([make('tf32'),make('fp16'),make('bf16'),make('int8')],
                          config={'frontend':'qe'},allow_errors=True)
        self.assertTrue(all('error' in result for result in rejected))

    def test_inactive_ports_and_negative_zero(self):
        rng=random.Random(0xB17)
        for profile in PROFILES:
            requests=[random_request(mode,rng,16,index) for index in range(12)
                      for mode,datatype in DTYPES.items() if not extended(profile,datatype)]
            requests.append(make('fp16',a=[0x8000]*16,b=[0]*16,c=0x80000000))
            baseline=evaluate(requests)
            poisoned=[poison_inactive(req,profile) for req in requests]
            self.assertEqual(baseline,evaluate(poisoned,config={'frontend':profile}))
            self.assertEqual(baseline[-1]['d'],'80000000')

    def test_group_coordinates_and_windows(self):
        for profile in PROFILES:
            for mode, requests, _ in corpus(profile):
                for local,glob in ((27,40),(28,40),(32,64)):
                    cfg={'frontend':profile,'local_shift_mag_width':local,'global_signed_align_width':glob}
                    request=requests[0]
                    result=evaluate([request],config=cfg,trace=True)[0]
                    groups=result['trace'][4]['data']['groups']
                    active=len(groups) if extended(profile,request['a_datatype']) else 4
                    for group_index,token in enumerate(groups[:active]):
                        sub=dict(request)
                        for field,bits in [('a',64),('b',64),('a_scale',8),('b_scale',8),
                                           ('a_e1',4),('b_e1',4),('a_e2',2),('b_e2',2)]:
                            sub[field]=format((int(request[field],16)>>(bits*group_index))&((1<<bits)-1),'x')
                        sub['c']='00000000'
                        frontend='multi' if group_index<4 else 'qe' if qe_extension(profile) else 'e'
                        single=evaluate([sub],config=cfg|{'k_fp16':4,'frontend':frontend},trace=True)[0]
                        self.assertEqual(token,single['trace'][4]['data']['groups'][0])
                    aligned=list(map(int,result['trace'][5]['data']['aligned_tc']))
                    self.assertEqual(sum(aligned),int(result['trace'][6]['data']['sop_tc']))
                    self.assertEqual(result['trace'][6]['data']['width'],glob+(3 if profile=='t8h16q32e96' else 4))

    def test_mixed_cycle_switch_bubbles_reset(self):
        for profile in PROFILES:
            requests=[]
            for _, batch, _ in corpus(profile): requests.extend(batch[:3])
            random.Random(0x817).shuffle(requests)
            for index,request in enumerate(requests): request['id']=index
            values=evaluate(requests,config={'frontend':profile})
            expected_by_id={result['id']:result for result in values}
            commands=[]
            checks=[]
            pending={}
            for index in range(70):
                reset=index in (0,18)
                request=requests[index-1] if 0<index<=len(requests) else None
                accepted=request is not None and index%7!=0 and not reset
                if reset: pending.clear()
                due=pending.pop(index,None)
                if accepted: pending[index+8]=request['id']
                command=dict(op='step',reset=reset,a_valid=accepted,b_valid=accepted,c_valid=accepted)
                if request: command['request']=request
                commands.append(command)
                checks.append((accepted,due))
            for tick,(accepted,due) in zip(invoke(commands,config={'frontend':profile}),checks):
                self.assertEqual(tick['accepted'],accepted)
                self.assertEqual(tick['valid'],due is not None)
                if due is not None: self.assertEqual(tick['result'],expected_by_id[due])

if __name__ == '__main__': unittest.main()
