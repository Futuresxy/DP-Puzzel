"""Existing-format cutpoint, parameter, special-value and cycle contract tests."""
import copy
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import DEFAULT_CONFIG, evaluate, invoke, read_inputs, write_inputs, ROOT
from cases.common import make, random_request
from cases.import_legacy import EXISTING
from reference.exact import reference, error_bound_ok, FORMATS, DTYPES, unpack, power


class ExistingModel(unittest.TestCase):
    def check_requests(self,requests,config=None,trace=False):
        cfg=DEFAULT_CONFIG | (config or {})
        got=evaluate(requests,config=cfg,trace=trace)
        for req,res in zip(requests,got):
            with self.subTest(id=req['id'],datatype=req['a_datatype'],config=cfg):
                ref=reference(req,cfg,True)
                self.assertEqual(int(res['d'],16),ref['bits'])
                self.assertEqual(res['flags']['invalid'],ref['value'].invalid)
                self.assertIsNot(error_bound_ok(int(res['d'],16),reference(req,cfg),ref),False)
                self.assertEqual(res['flags']['local_truncated'],ref['local_loss'])
                self.assertEqual(res['flags']['global_truncated'],ref['global_loss'])
        return got

    def test_random_parameter_profiles(self):
        rng=random.Random(0xD2027)
        for k in (4,8,16):
            requests=[random_request(mode,rng,k,i) for mode in EXISTING for i in range(40)]
            for local,global_width,extra in ((27,40,0),(28,48,0),(32,64,1)):
                self.check_requests(requests,dict(k_fp16=k,local_shift_mag_width=local,
                    global_signed_align_width=global_width,post_scale_norm_extra_stage=extra))

    def test_all_small_codes_and_scales(self):
        requests=[]
        for mode in EXISTING[2:]:
            dt=DTYPES[mode]; _,eb,fb,_,_,gn=FORMATS[dt]
            for code in range(1<<(1+eb+fb) if dt!=9 else 16):
                meta=([1]*4,[1,0,1,0],[0,1],[1,0]) if dt==9 else None
                requests.append(make(mode,4,a=[code]+[0]*(gn-1),metadata=meta,ident=len(requests)))
            if dt in (3,8,9):
                for code in range(128 if dt==8 else 256):
                    requests.append(make(mode,4,sa=[code],sb=[code],ident=len(requests)))
        self.check_requests(requests,dict(k_fp16=4))

    def test_ieee_directed(self):
        cases=[]
        def add(a,b,c,expected,invalid=False,**flags):
            r=make('bf16',4,a=a,b=b,c=c,ident=len(cases))
            cases.append((r,expected,dict(invalid=invalid,**flags)))
        one=0x3f80; posinf=0x7f80; neginf=0xff80
        add([posinf,0,0,0],[0,one,one,one],0,0x7fc00000,True)
        add([posinf,neginf,0,0],[one]*4,0,0x7fc00000,True)
        add([0x7fc0,posinf,neginf,0],[one]*4,0,0x7fc00000,True)
        add([0x7f81,0,0,0],[one]*4,0,0x7fc00000,True)
        add([0x7fc1,0,0,0],[one]*4,0,0x7fc00000)
        add([posinf,0,0,0],[one]*4,0xff800000,0x7fc00000,True)
        add([neginf,0,0,0],[one]*4,0,0xff800000)
        add([0x8000]*4,[one]*4,0x80000000,0x80000000)
        add([one,one|0x8000,0,0],[one]*4,0x80000000,0)
        add([0]*4,[one]*4,0x7f800001,0x7fc00000,True)
        # 2^-24 + C is an exact RNE tie at 1.0, exercise even/odd low bit.
        add([115<<7,0,0,0],[115<<7,one,one,one],0x3f800000,0x3f800000,inexact=True)
        add([115<<7,0,0,0],[115<<7,one,one,one],0x3f800001,0x3f800002,inexact=True)
        # BF16 minimum subnormal * 2^-17 = half FP32 minimum subnormal.
        add([1,0,0,0],[110<<7,one,one,one],0,0,inexact=True,underflow=True)
        add([1,0,0,0],[110<<7,one,one,one],0x007fffff,0x00800000,inexact=True,underflow=False)
        add([1,0,0,0],[111<<7,one,one,one],0,1,inexact=False,underflow=False)
        add([179<<7,0,0,0],[178<<7,one,one,one],0x7f7fffff,0x7f800000,inexact=True,overflow=True)
        got=self.check_requests([x[0] for x in cases],dict(k_fp16=4))
        for res,(_,bits,flags) in zip(got,cases):
            self.assertEqual(int(res['d'],16),bits)
            for flag,value in flags.items(): self.assertEqual(res['flags'][flag],value,(flag,res))

    def test_shared_scale_and_fused_shift(self):
        rng=random.Random(20271104)
        requests=[random_request(mode,rng,ident=i) for mode in EXISTING for i in range(12)]
        got=self.check_requests(requests,trace=True)
        seen=set()
        for req,res in zip(requests,got):
            s5=res['trace'][4]['data']; s6=res['trace'][5]['data']
            for p in s5['scale_multiplier']:
                self.assertEqual([p[x] for x in ('sop_magnitude_bits','coefficient_bits','product_bits')],[14,8,22])
                self.assertGreaterEqual(int(p['sop_magnitude']),0)
                self.assertEqual(int(p['product']),int(p['sop_magnitude'])*int(p['coefficient']))
            for t,control,y in zip(s5['groups']+[s5['c']],s6['controls'],s6['aligned_tc']):
                if t['zero'] or any(t['special'].values()): continue
                z,d,net=control['z'],control['d'],control['net']
                self.assertEqual(net,z-d); self.assertGreaterEqual(d,0)
                mag=int(t['m'])<<(39-t['width'])
                self.assertEqual(abs(int(y)),(mag<<z)>>d)
                seen.add((net>0)-(net<0))
        self.assertEqual(seen,{-1,0,1})

    def test_unsigned_scale_boundaries(self):
        c_negative_zero=0x80000000
        nv=[15]*64
        positive=[7]*64
        max_nv_scale=[0x77]*4
        hif_meta=([1]*16,[1]*16,[0]*8,[0]*8)
        cases=[
            (make('nvfp4',a=nv,b=positive,sa=max_nv_scale,sb=max_nv_scale,ident=0),9216,225,True),
            (make('hif4',a=nv,b=positive,sa=[195],sb=[195],metadata=hif_meta,ident=1),12544,196,True),
            (make('nvfp4',a=nv,b=positive,c=c_negative_zero,sa=[0]*4,ident=2),9216,0,True),
            (make('nvfp4',a=[8]*64,b=positive,c=c_negative_zero,ident=3),0,64,True),
            (make('nvfp4',a=([15]*8+[7]*8)*4,b=positive,c=c_negative_zero,ident=4),0,64,False),
        ]
        results=self.check_requests([r for r,_,_,_ in cases],trace=True)
        for res,(_,magnitude,coefficient,negative) in zip(results,cases):
            s5=res['trace'][4]['data']
            for p,token in zip(s5['scale_multiplier'],s5['groups']):
                self.assertEqual((int(p['sop_magnitude']),int(p['coefficient'])),(magnitude,coefficient))
                self.assertEqual(int(p['product']),magnitude*coefficient)
                self.assertEqual(int(token['m']),(magnitude*coefficient)<<(token['width']-22))
                self.assertEqual(token['sign'],negative)
            if magnitude*coefficient==0:
                self.assertEqual(int(res['d'],16),c_negative_zero if negative else 0)

    def test_cycle_stream_reset_and_illegal_tuple(self):
        rng=random.Random(2027)
        requests=[random_request(m,rng,ident=i) for i,m in enumerate(EXISTING*3)]
        for extra in (0,1):
            latency=8+extra; config=dict(post_scale_norm_extra_stage=extra)
            commands=[]; pending={}; expected=[]
            def push(req=None,valids=(False,False,False),reset=False,legal=True):
                cycle=len(commands); item=dict(op='step',a_valid=valids[0],b_valid=valids[1],c_valid=valids[2],reset=reset)
                if req is not None: item['request']=req
                if reset: pending.clear()
                out=pending.pop(cycle,None)
                accepted=all(valids) and legal and not reset
                if accepted: pending[cycle+latency]=req
                commands.append(item); expected.append((out,accepted))
            for i,r in enumerate(requests):
                if i==5: push(r,(True,False,True))
                if i==10: push(reset=True)
                if i==15:
                    bad=copy.deepcopy(r); bad['b_datatype']=99
                    push(bad,(True,True,True),legal=False)
                push(r,(True,True,True))
            for _ in range(latency): push()
            got=invoke(commands,config=config,trace=True)
            for tick,(req,accepted) in zip(got,expected):
                self.assertEqual(tick['accepted'],accepted)
                self.assertEqual(tick['valid'],req is not None)
                if req:
                    r=tick['result']; self.assertEqual(r['id'],req['id']); self.assertEqual(r['last'],req['last'])
                    self.assertEqual(int(r['d'],16),reference(req,DEFAULT_CONFIG|config,True)['bits'])
                    self.assertEqual(len(r['trace']),latency)
            self.assertTrue(any(t['protocol_error'] for t in got))
            # Each token's cutpoint advances at its own actual register boundary.
            first=got[0]['registers_after_edge'][0]
            self.assertEqual(first['cutpoint']['operation'],'unpack')
            self.assertEqual(got[4]['registers_after_edge'][4]['cutpoint']['stage'],5)

    def test_payload_rejection_and_vector_roundtrip(self):
        valid=make('fp16'); bad=[]
        for field,value in [('a_datatype',100),('a_datatype',1+(1<<32)),('id',-1),('b_datatype',2),('c_datatype',1),('a_scale','1'),('a_e1','1'),('c','100000000'),('a','1'+'0'*64)]:
            r=valid.copy(); r[field]=value; bad.append(r)
        r=make('mxfp6_e3m2'); r['a']=format(int(r['a'],16)|1,'x'); bad.append(r)
        r=make('mxfp8_e4m3'); r['a_scale']='7f7f7f7e'; bad.append(r)
        r=make('nvfp4'); r['a_scale']='b8b8b8b8'; bad.append(r)
        results=evaluate(bad,allow_errors=True)
        self.assertTrue(all('error' in r for r in results))
        path=ROOT/'test/runs/cmodel/roundtrip.txt'
        write_inputs(path,[valid],16); k,decoded=read_inputs(path)
        self.assertEqual(k,16); self.assertEqual(evaluate(decoded),evaluate([valid]))
        for cfg in (dict(k_fp16=12),dict(k_fp16=16.5),dict(local_shift_mag_width=26),dict(global_signed_align_width=32),dict(post_scale_norm_extra_stage=2),dict(unknown_width=40)):
            with self.assertRaises(RuntimeError): invoke([dict(op='config')],config=cfg)


if __name__=='__main__': unittest.main()
