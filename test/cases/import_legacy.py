"""Convert the selected read-only legacy corpus to the current packed DP ports."""
import argparse
from pathlib import Path
import json
import sys

TEST=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TEST))
from adapters.cmodel import ROOT, sha256, write_inputs
from reference.exact import DTYPES, FORMATS

EXISTING=('fp16','bf16','mxfp8_e4m3','mxfp8_e5m2','mxfp6_e3m2',
          'mxfp6_e2m3','mxfp4_e2m1','nvfp4','hif4')


def pack(values,width):
    if any(v<0 or v>=1<<width for v in values): raise ValueError('packed element out of range')
    return format(sum(v<<(i*width) for i,v in enumerate(values)),'x')


def request_from_elements(mode,a,b,c,scales_a=(),scales_b=(),e1a=(),e1b=(),e2a=(),e2b=(),
                          ident=0,last=False,k_fp16=16):
    dt=DTYPES[mode]; storage=FORMATS[dt][4]; group_n=FORMATS[dt][5]; groups=k_fp16//4
    if len(a)!=groups*group_n or len(b)!=len(a): raise ValueError('element count mismatch')
    if dt in (5,6): a=[v<<2 for v in a]; b=[v<<2 for v in b]
    kind=0 if dt in (0,1,2,10) else 2 if dt==8 else 3 if dt==9 else 1
    grain=16 if dt==8 else 64 if dt==9 else 32
    def broadcast(values):
        if kind==0:
            if values: raise ValueError('unexpected scale')
            return '0'
        expected=(len(a)+grain-1)//grain
        if len(values)!=expected: raise ValueError('source scale count mismatch')
        return pack([values[(g*group_n)//grain] for g in range(groups)],8)
    if dt==9 and (len(e1a)!=len(a)//4 or len(e1b)!=len(a)//4 or
                  len(e2a)!=len(a)//8 or len(e2b)!=len(a)//8):
        raise ValueError('HiF metadata count mismatch')
    return dict(id=ident,a_datatype=dt,b_datatype=dt,c_datatype=int(dt==10),
                a_scale_datatype=kind,b_scale_datatype=kind,last=last,
                a=pack(a,storage),b=pack(b,storage),c=f'{c:08x}',
                a_scale=broadcast(scales_a),b_scale=broadcast(scales_b),
                a_e1=pack(e1a,1),a_e2=pack(e2a,1),b_e1=pack(e1b,1),b_e2=pack(e2b,1))


def import_existing(source_root,dest_root=None):
    source=Path(source_root).resolve(strict=True)
    dest=Path(dest_root or TEST/'data/dp'); directories=[]
    for mode in EXISTING:
        dt=DTYPES[mode]; k=4*FORMATS[dt][5]
        src=source/mode/f'K{k}'/'correct_961'
        meta=json.loads((src/'case.json').read_text()); lines=(src/'inputs.txt').read_text().splitlines()
        if lines[0]!='PE_VECTORS_V2' or meta['logical_k']!=k: raise ValueError('legacy identity mismatch')
        header=[meta[key] for key in ('txn_count','logical_k','a_data_type','b_data_type','a_sf_type',
                                     'b_sf_type','c_type','out_type','rm','a_scale_count','b_scale_count',
                                     'group0_count','group1_count')]
        if list(map(int,lines[1].split()))!=header: raise ValueError('legacy header mismatch')
        ns=meta['a_scale_count']; g0=meta['group0_count']; g1=meta['group1_count']; requests=[]
        if ns!=meta['b_scale_count']: raise ValueError('unsupported unequal source scale counts')
        for i,line in enumerate(lines[2:]):
            v=[int(x,16) for x in line.split()]
            if len(v)!=2+2*k+2*ns+2*g0+2*g1 or v[0]!=i: raise ValueError('legacy row mismatch')
            off=2+2*k; sa=v[off:off+ns]; sb=v[off+ns:off+2*ns]; off+=2*ns
            a0=v[off:off+g0]; b0=v[off+g0:off+2*g0]; off+=2*g0
            a1=v[off:off+g1]; b1=v[off+g1:off+2*g1]
            requests.append(request_from_elements(mode,v[2:2+k],v[2+k:2+2*k],v[1],sa,sb,a0,b0,a1,b1,
                                                  ident=i,last=i==meta['txn_count']-1))
        if len(requests)!=meta['txn_count']: raise ValueError('legacy count mismatch')
        gold=(src/'golden.txt').read_text().splitlines()
        if len(gold)!=len(requests): raise ValueError('legacy golden count mismatch')
        out=dest/mode/f'K{k}'/'correct_961'; out.mkdir(parents=True,exist_ok=True)
        write_inputs(out/'inputs.txt',requests,16)
        (out/'source_reference.txt').write_text('\n'.join(gold)+'\n')
        manifest=dict(schema='dp_inputs_v1',format=mode,logical_k=k,k_fp16=16,count=len(requests),
                      segments=meta['segments'],source_golden_model=meta['golden_model'],
                      sources={n:dict(path=str((src/n).relative_to(source)),sha256=sha256(src/n))
                               for n in ('case.json','inputs.txt','golden.txt')},
                      input_sha256=sha256(out/'inputs.txt'),reference_sha256=sha256(out/'source_reference.txt'),
                      input_layout='test/data/README.md',legacy_thresholds_adopted=False)
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        directories.append(out)
    return directories


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True, help='External legacy vector corpus')
    args=parser.parse_args()
    for p in import_existing(args.source_root): print(p.relative_to(ROOT))
