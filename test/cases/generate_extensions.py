"""TF32 K8 and INT8 K32 extensions; run after the existing-format campaign."""
from pathlib import Path
import json
import random
import sys

TEST=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TEST))
from adapters.cmodel import write_inputs, sha256
from cases.common import make, random_request
from cases.import_legacy import pack

SEED=20271104


def generate():
    outputs=[]
    for mode,k in (('tf32',8),('int8',32)):
        rng=random.Random(SEED); requests=[]; segments=[]
        def append_segment(name,values,exact=False):
            start=len(requests)
            for r in values:
                r['id']=len(requests); requests.append(r)
            segments.append(dict(dataset=name,start=start,stop=len(requests),require_bit_exact=exact))
        append_segment('full_encoding_random',[random_request(mode,rng,ident=i) for i in range(512)],mode=='int8')
        values=[]
        for _ in range(512):
            if mode=='tf32':
                raw=lambda:(rng.getrandbits(1)<<31)|(rng.randrange(110,145)<<23)|(rng.getrandbits(10)<<13)
                c=(rng.getrandbits(1)<<31)|(rng.randrange(100,150)<<23)|rng.getrandbits(23)
                values.append(make(mode,a=[raw() for _ in range(k)],b=[raw() for _ in range(k)],c=c))
            else:
                c=rng.choice((0x7fffffff,0x80000000,0,0xffffffff))
                values.append(make(mode,a=[rng.randrange(256) for _ in range(k)],b=[rng.randrange(256) for _ in range(k)],c=c))
        append_segment('finite_random_and_accumulator_boundaries',values,mode=='int8')
        values=[]
        if mode=='tf32':
            codes=[0,0x80000000,0x2000,0x007fe000,0x00800000,0x3f800000,
                   0xbf800000,0x7f7fe000,0x7f800000,0xff800000,0x7f802000,0x7fc00000]
            for code in codes:
                values.append(make(mode,a=[code]+[0]*(k-1)))
                values.append(make(mode,a=[code]*k,b=[code]*k))
            values.extend([make(mode,a=[0x7f800000,0xff800000]+[0]*(k-2)),
                           make(mode,a=[0x80000000]*k,c=0x80000000),
                           make(mode,a=[0x7f800000]*k,b=[0]*k),
                           make(mode,a=[0x3f800000,0xbf800000]+[0]*(k-2))])
        else:
            for a,b in ((128,128),(128,127),(127,127),(255,1),(0,0)):
                for c in (0,0x7fffffff,0x80000000,0xffffffff):
                    values.append(make(mode,a=[a]*k,b=[b]*k,c=c))
        append_segment('directed_boundaries',values,mode=='int8')
        append_segment('ones',[make(mode)],True)
        requests[-1]['last']=True
        out=TEST/'data/dp'/mode/f'K{k}'/'generated_v1'; out.mkdir(parents=True,exist_ok=True)
        write_inputs(out/'inputs.txt',requests,16)
        manifest=dict(schema='dp_inputs_v1',format=mode,logical_k=k,k_fp16=16,count=len(requests),
                      generator='test/cases/generate_extensions.py',generator_sha256=sha256(__file__),
                      seed=SEED,segments=segments,input_layout='test/data/README.md',
                      input_sha256=sha256(out/'inputs.txt'),
                      reference='FP64 math.fsum plus exact Fraction' if mode=='tf32' else 'Python unbounded signed integer + modulo 2^32')
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n'); outputs.append(out)
    return outputs


if __name__=='__main__':
    for p in generate(): print(p)
