#!/usr/bin/env python3
"""Compile the hand-written DP and replay shared packed vectors against CModel.

No numerical repacking occurs. The Verilog TB reads DP_INPUTS_V1 and checks timing,
atomic handshake, last, result type and every result bit. Artifacts stay in runs/.
"""
from pathlib import Path
import argparse
import json
import random
import subprocess
import sys
import hashlib
import os
from itertools import product
from datetime import datetime, timezone

sys.path.insert(0,str(Path(__file__).resolve().parent))
from adapters.cmodel import ROOT, read_inputs, write_inputs, evaluate
from cases.common import random_request, make
from reference.exact import DTYPES, ulp_distance
from reference.architecture import reference
from adapters.rtl import snapshot, record_validation
from dp_rtl_gate import CONFIGS, DEFAULT_SCOPE

RUN=ROOT/'test/runs/verilog'
TESTBENCH=ROOT/'test/rtl_tb/dp_tb.v'
SIMULATOR='verilator'
IMPLEMENTATION='verilog'
VERILATOR='verilator'
EXPORT=None
SOURCE_LIST=None
FRONTEND='multi'
V19_PROFILES=('t8h16q32e96','t8h16q32e128','t8h16q64e128_opt','q32e64')
E_MODES=('mxfp4_e2m1','nvfp4','hif4')

def run(cmd,log):
    proc=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
    log.write_text(proc.stdout+proc.stderr)
    if proc.returncode:
        raise RuntimeError(f'{cmd[0]} failed: {log}\n{(proc.stdout+proc.stderr)[-5000:]}')
    return proc.stdout

def compile_tb(k,local,glob):
    build=RUN/f'{SIMULATOR}-{IMPLEMENTATION}-k{k}-l{local}-g{glob}'
    build.mkdir(parents=True,exist_ok=True)
    files=str(SOURCE_LIST)
    lint=['-Wall','-Wno-UNUSEDSIGNAL','-Wno-UNUSEDPARAM','-Wno-VARHIDDEN']
    language=['--language','1364-2005'] if IMPLEMENTATION=='verilog' else []
    top='dp_top_e' if FRONTEND=='e' else 'dp_top'
    define=['-DDP_E_FRONTEND'] if FRONTEND=='e' else ['-DDP_LEGACY_SV'] if IMPLEMENTATION=='systemverilog' else []
    if SIMULATOR=='verilator':
        run([VERILATOR,'--lint-only',*lint,*language,'--top-module',top,'-f',files,
             f'-GK_FP16={k}',f'-GLOCAL_W={local}',f'-GGLOBAL_W={glob}'],build/'lint.log')
        exe=build/'Vdp_tb'
        run([VERILATOR,'--binary','--timing','-j','2',*language,*define,
             '-Wno-WIDTH','-Wno-TIMESCALEMOD','-Wno-INITIALDLY',
             '--top-module','dp_tb','--Mdir',str(build),
             f'-GK_FP16={k}',f'-GLOCAL_W={local}',f'-GGLOBAL_W={glob}',
             '-I'+str(EXPORT/'src/src/verilog/parameter'),'-I'+str(TESTBENCH.parent),'-f',files,str(TESTBENCH)],build/'compile.log')
    else:
        exe=build/'dp_tb.vvp'
        run(['iverilog','-g2005' if IMPLEMENTATION=='verilog' else '-g2012',*define,'-I'+str(EXPORT/'src/src/verilog/parameter'),'-I'+str(TESTBENCH.parent),
             '-s','dp_tb',f'-Pdp_tb.K_FP16={k}',f'-Pdp_tb.LOCAL_W={local}',
             f'-Pdp_tb.GLOBAL_W={glob}','-o',str(exe),'-f',files,str(TESTBENCH)],build/'compile.log')
    return exe

def campaign(name,k,local,glob,requests,exe,source=None,expected=None,stress=False,observe=False):
    dest=RUN/f'{SIMULATOR}-{IMPLEMENTATION}'/name; dest.mkdir(parents=True,exist_ok=True)
    inp=Path(source) if source else dest/'inputs.txt'
    if not source: write_inputs(inp,requests,k)
    if expected is None:
        valid=[r for r in requests if legal_tuple(r)]
        responses=iter(evaluate(valid,trace=True,config=dict(frontend=FRONTEND,architecture_v19=FRONTEND in V19_PROFILES,k_fp16=k,local_shift_mag_width=local,global_signed_align_width=glob),run_dir=dest))
        expected=[next(responses) if legal_tuple(r) else dict(d='00000000') for r in requests]
    gold=dest/'golden.txt'; gold.write_text(''.join(r['d']+'\n' for r in expected))
    schedule=[]
    for i,r in enumerate(requests):
        if stress and i%17==0:
            schedule += [f'0 1 0 0 {i}',f'0 1 1 0 {i}']
        if stress and i%83==0: schedule.append(f'1 1 1 1 {i}')
        schedule.append(f'0 1 1 1 {i}')
        if stress and i%13==0: schedule.append(f'0 0 0 0 {i}')
    schedule += ['0 0 0 0 -1']*8
    sched=dest/'schedule.txt'; sched.write_text('\n'.join(schedule)+'\n')
    command=([str(exe)] if SIMULATOR=='verilator' else ['vvp',str(exe)])
    out=run(command+([f'+CUTPOINTS={dest / "cutpoints.txt"}'] if stress or observe else [])+[f'+INPUTS={inp}',f'+GOLDEN={gold}',f'+SCHEDULE={sched}',f'+OUTPUT={dest / "results.txt"}'],dest/'simulation.log')
    line=next((s for s in out.splitlines() if s.startswith('PASS cycles=')),None)
    if line is None:
        raise RuntimeError(f'{name} FAIL: see {dest / "simulation.log"}')
    outputs=check_schedule(schedule,requests,expected,(dest/'results.txt').read_text())
    cutpoints=check_cutpoints(dest/'cutpoints.txt',expected,requests) if stress or observe else 0
    metrics={}
    if stress:
        print(f'  {name:<21} {line.replace(" cancelled=", " reset_cancelled=")}',flush=True)
    else:
        metrics=precision_metrics(outputs,expected)
        precision=name.upper().replace('_',' ')
        count=len(outputs)
        max_ulp=metrics['max_ulp'] if metrics['max_ulp'] is not None else 'n/a'
        print(f'  {precision:<16} PASS  golden_exact={count}/{count}  '
              f'math_exact={metrics["math_exact"]}/{count}  max_ulp={max_ulp}',flush=True)
    return dict(export_id=EXPORT.name,frontend=FRONTEND,simulator=SIMULATOR,implementation=IMPLEMENTATION,name=name,k_fp16=k,local_width=local,global_width=glob,cutpoints_checked=cutpoints,simulation_log=str((dest/'simulation.log').relative_to(ROOT)), lint_log=str((exe.parent/'lint.log').relative_to(ROOT)), compile_log=str((exe.parent/'compile.log').relative_to(ROOT)), results_path=str((dest/'results.txt').relative_to(ROOT)), input_path=str(inp.relative_to(ROOT)), golden_path=str(gold.relative_to(ROOT)), schedule_path=str(sched.relative_to(ROOT)), output_sha256=hashlib.sha256((dest/"results.txt").read_bytes()).hexdigest(),input_sha256=hashlib.sha256(inp.read_bytes()).hexdigest(),result=line,**metrics)

def precision_metrics(outputs,expected):
    math_bits={r['id']:int(r['exact_fp32_or_int32'],16) for r in expected}
    math_exact=0
    distances=[]
    nonfinite=0
    for ident,bits,result_type,_ in outputs:
        reference=math_bits[ident]
        math_exact+=bits==reference
        if result_type==0:
            if any((value & 0x7f800000)==0x7f800000 for value in (bits,reference)):
                nonfinite+=1
            else:
                distances.append(ulp_distance(bits,reference))
    return dict(golden_exact=len(outputs),math_exact=math_exact,
                max_ulp=max(distances,default=None),fp32_ulp_count=len(distances),
                nonfinite_fp32_count=nonfinite)

def legal_tuple(r):
    t=r['a_datatype']
    scale=0 if t in (0,1,2,10) else 1 if t in (3,4,5,6,7) else 2 if t==8 else 3
    return 0<=t<=10 and (FRONTEND not in ('e','e64') or t in (7,8,9)) and (FRONTEND!='q32e64' or 3<=t<=9) and r['b_datatype']==t and r['c_datatype']==int(t==10) and r['a_scale_datatype']==scale and r['b_scale_datatype']==scale

def check_schedule(schedule,requests,expected,actual):
    pipeline=[None]*8; want=[]
    for line in schedule:
        reset,av,bv,cv,row=map(int,line.split())
        if reset:
            pipeline=[None]*8
            continue
        emitted=pipeline.pop(); pipeline.insert(0,None)
        if emitted is not None:
            r=requests[emitted]
            want.append((r['id'],int(expected[emitted]['d'],16),r['c_datatype'],int(r['last'])))
        if av and bv and cv and row>=0 and legal_tuple(requests[row]): pipeline[0]=row
    got=[(int(r[0]),int(r[1],16),int(r[2]),int(r[3])) for r in map(str.split,actual.splitlines())]
    if got!=want: raise AssertionError('RTL output stream differs from independent schedule oracle')
    return got

def check_cutpoints(path,results,requests):
    count=0
    for line in path.read_text().splitlines():
        row,stage,kind,index,*values=line.split()
        row,stage,index=int(row),int(stage),int(index)
        trace=results[row]['trace'][stage-1]['data']
        if kind.startswith('frontend_') and kind!='frontend_group_mag':
            group_index=index//8 if kind in ('frontend_leaf','frontend_pair') else index//2
            local_index=index%8 if kind in ('frontend_leaf','frontend_pair') else index%2
            local_trace=trace['frontends'][group_index]['data'] if 'frontends' in trace else trace
            if 'frontends' not in trace: local_index=index
            if kind=='frontend_pair':
                want=[int(local_trace['pairs_tc'][local_index//4][local_index%4])]
            elif kind=='frontend_leaf':
                leaves=local_trace['leaves_tc'][local_index//4]
                want=[int(leaves[local_index%4]) if local_index%4<len(leaves) else 0]
            else:
                want=[int(local_trace['sop_tc'][local_index])]
            got=[int(values[0])]
        elif kind=='frontend_group_mag':
            local_trace=trace['frontends'][index]['data']
            want=[int(local_trace['magnitude'][0]),int(local_trace['sign'][0])]
            got=[int(values[0],16),int(values[1])]
        elif kind=='e_lzd22':
            token=results[row]['trace'][4]['data']['groups'][index]
            magnitude=int(token['m']) >> (token['width']-22)
            want=[magnitude,22-magnitude.bit_length() if magnitude else 0]
            got=[int(values[0],16),int(values[1])]
        elif kind in ('e_a','e_b'):
            atom=trace['a' if kind=='e_a' else 'b'][index]
            want=[int(atom['m']),int(atom['sign'])]; got=[int(values[0],16),int(values[1])]
        elif kind=='e_pair':
            want=[int(trace['pairs_tc'][index//4][index%4])]; got=[int(values[0])]
        elif kind=='e_control':
            want=[trace['lane_shift'][index],int(trace['all_negative'][index])]; got=list(map(int,values))
        elif kind=='e_lane':
            want=[int(trace['sop_tc'][index])]; got=[int(values[0])]
        elif kind=='e_group':
            want=[int(trace['magnitude'][index]),int(trace['sign'][index])]; got=[int(values[0],16),int(values[1])]
        elif kind in ('layout_a','layout_b'):
            atom=trace['a_layout' if kind=='layout_a' else 'b_layout'][index]
            want=[atom['M'],atom['E'],atom['S']]; got=[int(v,16) for v in values]
        elif kind=='product': want=[int(trace['products'][index]['m'])]; got=[int(values[0],16)]
        elif kind=='anchor': want=[trace['r'][index]]; got=[int(values[0],16)]
        elif kind=='raw_anchor':
            token=results[row]['trace'][4]['data']['groups'][index]
            # S3 candidate is unmasked; S5 clears inactive/INT anchors. Compare finite active groups.
            if requests[row]['c_datatype'] or token['zero'] or any(token['special'].values()): continue
            want=[token['anchor_raw']]; got=[int(values[0])]
        elif kind=='compare_exp':
            want=[trace['groups'][index]['compare_exp']]; got=[int(values[0])]
        elif kind=='leaf':
            leaves=trace['leaves_tc'][index//4]; j=index%4
            want=[int(leaves[j]) if j<len(leaves) else 0]; got=[int(values[0])]
        elif kind=='lane': want=[int(trace['sop_tc'][index])]; got=[int(values[0])]
        elif kind in ('group','c'):
            token=trace['groups'][index] if kind=='group' else trace['c']
            flags=token['special']; sf=(int(flags['nan'])<<3)|(int(flags['invalid'])<<2)|(int(flags['positive_inf'])<<1)|int(flags['negative_inf'])
            want=[int(token['m']),token['anchor_raw'],token['z'],int(token['sign']),sf]
            got=[int(values[0],16),int(values[1]),int(values[2]),int(values[3]),int(values[4],16)]
        elif kind=='aligned': want=[int(trace['aligned_tc'][index]),trace['E_max']]; got=list(map(int,values))
        elif kind=='sum': want=[int(trace['sop_tc'])]; got=[int(values[0])]
        else: raise ValueError(kind)
        if got!=want: raise AssertionError(f'{path}: row {row} stage {stage} {kind}[{index}] {got} != {want}')
        count+=1
    if count==0: raise AssertionError('no cutpoint observations')
    return count

def e_directed(k):
    """All nibble products/e1/e2, plus cancellation, scales and FP32 C edges."""
    req=[]; n=4*k
    for mode in E_MODES:
        metadata=product((0,1),repeat=4) if mode=='hif4' else [(0,0,0,0)]
        for e1a,e1b,e2a,e2b in metadata:
            meta=([e1a]*(n//4),[e1b]*(n//4),[e2a]*(n//8),[e2b]*(n//8)) if mode=='hif4' else None
            for a,b in product(range(16),repeat=2):
                req.append(make(mode,k,a=[a]+[0]*(n-1),b=[b]+[0]*(n-1),metadata=meta))
        for code in range(128 if mode=='nvfp4' else 256):
            count=(n+15)//16 if mode=='nvfp4' else (n+31)//32 if mode=='mxfp4_e2m1' else (n+63)//64
            req.append(make(mode,k,sa=[code]*count,sb=[code]*count))
        for c in (0,0x80000000,1,0x007fffff,0x00800000,0x7f7fffff,
                  0x7f800000,0xff800000,0x7fc00000,0x7f800001):
            req.append(make(mode,k,c=c))
        req.append(make(mode,k,a=[15]*n,b=[7]*n))
        req.append(make(mode,k,a=[8]*n,b=[7]*n,c=0x80000000))
        req.append(make(mode,k,a=([15]*8+[7]*8)*(n//16),b=[7]*n,c=0x80000000))
    req.append(make('hif4',k,a=[15]*n,b=[7]*n,
                    metadata=([1]*(n//4),[1]*(n//4),[1]*(n//8),[1]*(n//8))))
    for i,r in enumerate(req): r.update(id=i,last=i%7==0)
    return req

def main():
    global SIMULATOR,IMPLEMENTATION,VERILATOR,EXPORT,SOURCE_LIST,RUN,FRONTEND
    ap=argparse.ArgumentParser()
    ap.add_argument('--phase',choices=['existing','parameters','all'],default='all')
    ap.add_argument('--frontend',choices=['multi','e'],default='multi')
    ap.add_argument('--simulator',choices=['verilator','iverilog'],default='verilator')
    ap.add_argument('--implementation',choices=['verilog','systemverilog','both'],default='verilog',
                    help='RTL implementation (default: %(default)s); systemverilog/both are explicit legacy-reference checks')
    ap.add_argument('--verilator',default=os.environ.get('VERILATOR','verilator'))
    ap.add_argument('--local-w',type=int,default=DEFAULT_SCOPE[1],help='S3 unsigned window (default: %(default)s)')
    ap.add_argument('--global-w',type=int,default=DEFAULT_SCOPE[2],help='S6 signed window (default: %(default)s)')
    args=ap.parse_args()
    FRONTEND=args.frontend
    if FRONTEND=='e' and args.implementation!='verilog': ap.error('E frontend requires pure Verilog')
    k_default=DEFAULT_SCOPE[0]
    selected=(k_default,args.local_w,args.global_w)
    custom=selected!=DEFAULT_SCOPE
    if args.local_w<27 or args.global_w<max(args.local_w+4,33):
        ap.error('require LOCAL_W >= 27 and GLOBAL_W >= max(LOCAL_W+4, 33)')
    config=dict(frontend=FRONTEND,k_fp16=k_default,local_shift_mag_width=args.local_w,global_signed_align_width=args.global_w)
    SIMULATOR=args.simulator; VERILATOR=args.verilator
    implementations=['verilog','systemverilog'] if args.implementation=='both' else [args.implementation]
    started=datetime.now(timezone.utc).isoformat()
    RUN=RUN/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    RUN.mkdir(parents=True,exist_ok=False); report=[]
    for IMPLEMENTATION in implementations:
        EXPORT,SOURCE_LIST=snapshot(IMPLEMENTATION,FRONTEND)
        if args.phase in ('existing','all'):
            print(f'\n{SIMULATOR} / {IMPLEMENTATION} / {FRONTEND}: per-precision results '
                  f'(K_FP16={k_default}, LOCAL_W={args.local_w}, GLOBAL_W={args.global_w})',flush=True)
            golden_source='recomputed' if custom else 'saved'
            print(f'  golden_exact uses {golden_source} finite-width CModel results. '
                  'math_exact and max_ulp use the exact mathematical reference.',flush=True)
            exe=compile_tb(*selected)
            for inp in sorted((ROOT/'test/data/dp').glob('*/*/*/inputs.txt')):
                if FRONTEND=='e' and inp.parts[-4] not in E_MODES: continue
                k,req=read_inputs(inp)
                if k!=k_default: raise ValueError(f'Unexpected K in {inp}')
                golden=[json.loads(s) for s in inp.with_name('expected.jsonl').read_text().splitlines()]
                if custom:
                    for row,result in zip(golden,evaluate(req,config=config,run_dir=RUN)):
                        row['d']=result['d']
                report.append(campaign(inp.parts[-4],*selected,req,exe,inp,golden))
        if args.phase in ('parameters','all'):
            print(f'\n{SIMULATOR} / {IMPLEMENTATION}: mixed-format parameter checks',flush=True)
            print('  reset_cancelled counts accepted requests cleared by reset before output.',flush=True)
            rng=random.Random(20271105)
            for k,local,glob in dict.fromkeys(selected if c==DEFAULT_SCOPE else c for c in CONFIGS):
                modes=E_MODES if FRONTEND=='e' else DTYPES
                req=[random_request(mode,rng,k,ident=i*len(modes)+j) for i in range(48) for j,mode in enumerate(modes)]
                for update in [dict(b_datatype=2),dict(a_datatype=15,b_datatype=15),dict(c_datatype=1),dict(a_scale_datatype=3),dict(b_scale_datatype=1)]:
                    bad=make('nvfp4' if FRONTEND=='e' else 'fp16',k,ident=len(req)); bad.update(update); req.append(bad)
                if FRONTEND=='e': req.append(make('fp16',k,ident=len(req)))
                exe=compile_tb(k,local,glob)
                report.append(campaign(f'mixed-k{k}-l{local}-g{glob}',k,local,glob,req,exe,stress=True))
        if FRONTEND=='e' and args.phase=='all':
            req=e_directed(k_default)
            cfg=config
            expected=evaluate(req,trace=True,config=cfg,run_dir=RUN/'directed-model')
            for r,result in zip(req,expected):
                result['exact_fp32_or_int32']=f'{reference(r,cfg,True)["bits"]:08x}'
            report.append(campaign('directed-e',*selected,req,compile_tb(*selected),expected=expected,observe=True))
        if FRONTEND=='multi' and IMPLEMENTATION=='verilog' and args.phase=='all':
            req=e_directed(k_default)
            for left in range(3):
                for right in range(3):
                    for negative in (False,True):
                        meta=([1]*16,[1]*16,[int(left>0),int(right>0)]*4,[int(left==2),int(right==2)]*4)
                        req.append(make('hif4',k_default,a=([7]*8+[15 if negative else 7]*8)*4,
                                        b=[7]*64,metadata=meta))
            for c in (1,0x007fffff,0x80000001,0x00800000):
                req.append(make('bf16',k_default,a=[0]*k_default,c=c))
                req.append(make('bf16',k_default,a=[1]+[0]*(k_default-1),b=[1]*k_default,c=c))
            for index,request in enumerate(req): request['id']=index
            expected=evaluate(req,trace=True,config=config,run_dir=RUN/'v18-directed-model')
            for request,result in zip(req,expected):
                # Exact golden remains independent of the finite-window architecture policy.
                result['exact_fp32_or_int32']=f'{reference(request,config)["bits"]:08x}'
            report.append(campaign('directed-v18',*selected,req,compile_tb(*selected),expected=expected,observe=True))
    test_sources=[Path(__file__),TESTBENCH,ROOT/'test/adapters/rtl.py']
    test_fingerprint=hashlib.sha256(b''.join(p.read_bytes() for p in test_sources)).hexdigest()
    if len(implementations)==2:
        halves=len(report)//2
        for a,b in zip(report[:halves],report[halves:]):
            if (a['name'],a['input_sha256'],a['output_sha256'])!=(b['name'],b['input_sha256'],b['output_sha256']):
                raise AssertionError('Verilog/SystemVerilog comparison mismatch')
    for export_id in sorted({r['export_id'] for r in report}):
        record_validation(ROOT/'hw/rtl'/export_id,[r for r in report if r['export_id']==export_id],test_fingerprint,
                          phase=args.phase,started=started,run_dir=RUN,
                          backend_scope=not custom,
                          command=[sys.executable,*sys.argv],
                          simulator_version=subprocess.check_output([VERILATOR,'--version'] if SIMULATOR=='verilator' else ['iverilog','-V'],text=True,stderr=subprocess.STDOUT).splitlines()[0])
    summary=RUN/f'{SIMULATOR}-{args.implementation}-{args.phase}-summary.json'
    summary.write_text(json.dumps(report,indent=2)+'\n')
    print(f'\nReport: {summary.relative_to(ROOT)}',flush=True)

if __name__=='__main__': main()
