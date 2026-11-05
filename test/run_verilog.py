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
from datetime import datetime, timezone

sys.path.insert(0,str(Path(__file__).resolve().parent))
from adapters.cmodel import ROOT, read_inputs, write_inputs, evaluate
from cases.common import random_request, make
from reference.exact import DTYPES, ulp_distance
from adapters.rtl import snapshot, record_validation

RUN=ROOT/'test/runs/verilog'
TESTBENCH=ROOT/'test/rtl_tb/dp_tb.v'
SIMULATOR='verilator'
IMPLEMENTATION='verilog'
VERILATOR='verilator'
EXPORT=None
SOURCE_LIST=None

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
    if SIMULATOR=='verilator':
        run([VERILATOR,'--lint-only',*lint,*language,'--top-module','dp_top','-f',files,
             f'-GK_FP16={k}',f'-GLOCAL_W={local}',f'-GGLOBAL_W={glob}'],build/'lint.log')
        exe=build/'Vdp_tb'
        run([VERILATOR,'--binary','--timing','-j','2',*language,
             '-Wno-WIDTH','-Wno-TIMESCALEMOD','-Wno-INITIALDLY',
             '--top-module','dp_tb','--Mdir',str(build),
             f'-GK_FP16={k}',f'-GLOCAL_W={local}',f'-GGLOBAL_W={glob}',
             '-I'+str(EXPORT/'src/src/verilog/parameter'),'-f',files,str(TESTBENCH)],build/'compile.log')
    else:
        exe=build/'dp_tb.vvp'
        run(['iverilog','-g2005' if IMPLEMENTATION=='verilog' else '-g2012','-I'+str(EXPORT/'src/src/verilog/parameter'),
             '-s','dp_tb',f'-Pdp_tb.K_FP16={k}',f'-Pdp_tb.LOCAL_W={local}',
             f'-Pdp_tb.GLOBAL_W={glob}','-o',str(exe),'-f',files,str(TESTBENCH)],build/'compile.log')
    return exe

def campaign(name,k,local,glob,requests,exe,source=None,expected=None,stress=False):
    dest=RUN/f'{SIMULATOR}-{IMPLEMENTATION}'/name; dest.mkdir(parents=True,exist_ok=True)
    inp=Path(source) if source else dest/'inputs.txt'
    if not source: write_inputs(inp,requests,k)
    if expected is None:
        valid=[r for r in requests if legal_tuple(r)]
        responses=iter(evaluate(valid,trace=True,config=dict(k_fp16=k,local_shift_mag_width=local,global_signed_align_width=glob)))
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
    out=run(command+([f'+CUTPOINTS={dest / "cutpoints.txt"}'] if stress else [])+[f'+INPUTS={inp}',f'+GOLDEN={gold}',f'+SCHEDULE={sched}',f'+OUTPUT={dest / "results.txt"}'],dest/'simulation.log')
    line=next((s for s in out.splitlines() if s.startswith('PASS cycles=')),None)
    if line is None:
        raise RuntimeError(f'{name} FAIL: see {dest / "simulation.log"}')
    outputs=check_schedule(schedule,requests,expected,(dest/'results.txt').read_text())
    cutpoints=check_cutpoints(dest/'cutpoints.txt',expected,requests) if stress else 0
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
    return dict(export_id=EXPORT.name,simulator=SIMULATOR,implementation=IMPLEMENTATION,name=name,k_fp16=k,local_width=local,global_width=glob,cutpoints_checked=cutpoints,simulation_log=str((dest/'simulation.log').relative_to(ROOT)), lint_log=str((exe.parent/'lint.log').relative_to(ROOT)), compile_log=str((exe.parent/'compile.log').relative_to(ROOT)), results_path=str((dest/'results.txt').relative_to(ROOT)), input_path=str(inp.relative_to(ROOT)), golden_path=str(gold.relative_to(ROOT)), schedule_path=str(sched.relative_to(ROOT)), output_sha256=hashlib.sha256((dest/"results.txt").read_bytes()).hexdigest(),input_sha256=hashlib.sha256(inp.read_bytes()).hexdigest(),result=line,**metrics)

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
    return 0<=t<=10 and r['b_datatype']==t and r['c_datatype']==int(t==10) and r['a_scale_datatype']==scale and r['b_scale_datatype']==scale

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
        if kind in ('layout_a','layout_b'):
            atom=trace['a_layout' if kind=='layout_a' else 'b_layout'][index]
            want=[atom['M'],atom['E'],atom['S']]; got=[int(v,16) for v in values]
        elif kind=='product': want=[int(trace['products'][index]['m'])]; got=[int(values[0],16)]
        elif kind=='anchor': want=[trace['r'][index]]; got=[int(values[0],16)]
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

def main():
    global SIMULATOR,IMPLEMENTATION,VERILATOR,EXPORT,SOURCE_LIST,RUN
    ap=argparse.ArgumentParser()
    ap.add_argument('--phase',choices=['existing','parameters','all'],default='all')
    ap.add_argument('--simulator',choices=['verilator','iverilog'],default='verilator')
    ap.add_argument('--implementation',choices=['verilog','systemverilog','both'],default='both')
    ap.add_argument('--verilator',default=os.environ.get('VERILATOR','verilator'))
    args=ap.parse_args()
    SIMULATOR=args.simulator; VERILATOR=args.verilator
    implementations=['verilog','systemverilog'] if args.implementation=='both' else [args.implementation]
    started=datetime.now(timezone.utc).isoformat()
    RUN=RUN/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    RUN.mkdir(parents=True,exist_ok=False); report=[]
    for IMPLEMENTATION in implementations:
        EXPORT,SOURCE_LIST=snapshot(IMPLEMENTATION)
        if args.phase in ('existing','all'):
            print(f'\n{SIMULATOR} / {IMPLEMENTATION}: per-precision results (K_FP16=16, LOCAL_W=27, GLOBAL_W=40)',flush=True)
            print('  golden_exact uses saved finite-width CModel results. '
                  'math_exact and max_ulp use the exact mathematical reference.',flush=True)
            exe=compile_tb(16,27,40)
            for inp in sorted((ROOT/'test/data/dp').glob('*/*/*/inputs.txt')):
                k,req=read_inputs(inp)
                golden=[json.loads(s) for s in inp.with_name('expected.jsonl').read_text().splitlines()]
                report.append(campaign(inp.parts[-4],k,27,40,req,exe,inp,golden))
        if args.phase in ('parameters','all'):
            print(f'\n{SIMULATOR} / {IMPLEMENTATION}: mixed-format parameter checks',flush=True)
            print('  reset_cancelled counts accepted requests cleared by reset before output.',flush=True)
            rng=random.Random(20271105)
            for k,local,glob in [(4,27,40),(8,27,40),(16,27,40),(4,28,48),(8,32,64),(16,32,64)]:
                req=[random_request(mode,rng,k,ident=i*len(DTYPES)+j) for i in range(48) for j,mode in enumerate(DTYPES)]
                for update in [dict(b_datatype=2),dict(a_datatype=15,b_datatype=15),dict(c_datatype=1),dict(a_scale_datatype=3),dict(b_scale_datatype=1)]:
                    bad=make('fp16',k,ident=len(req)); bad.update(update); req.append(bad)
                exe=compile_tb(k,local,glob)
                report.append(campaign(f'mixed-k{k}-l{local}-g{glob}',k,local,glob,req,exe,stress=True))
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
                          command=[sys.executable,*sys.argv],
                          simulator_version=subprocess.check_output([VERILATOR,'--version'] if SIMULATOR=='verilator' else ['iverilog','-V'],text=True,stderr=subprocess.STDOUT).splitlines()[0])
    summary=RUN/f'{SIMULATOR}-{args.implementation}-{args.phase}-summary.json'
    summary.write_text(json.dumps(report,indent=2)+'\n')
    print(f'\nReport: {summary.relative_to(ROOT)}',flush=True)

if __name__=='__main__': main()
