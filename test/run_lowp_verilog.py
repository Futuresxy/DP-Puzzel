#!/usr/bin/env python3
"""Four-group E64/Q32E64: native corpus, S5-S7 and L8 protocol on frozen RTL."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import run_verilog as shared
from adapters.cmodel import ROOT, evaluate, read_inputs
from adapters.rtl import snapshot, record_validation
from cases.common import make, random_request
from dp_rtl_gate import MIXED_CONFIGS, LOWP_PROFILES
from reference.exact import DTYPES


def compile_tb(profile, local, glob):
    build=shared.RUN/f'build-l{local}-g{glob}'
    build.mkdir(parents=True,exist_ok=True)
    top='dp_top_'+profile
    flags=['--language','1364-2005']
    shared.run([shared.VERILATOR,'--lint-only','-Wall','-Wno-UNUSEDSIGNAL','-Wno-UNUSEDPARAM',
                '-Wno-VARHIDDEN',*flags,'--top-module',top,'-f',str(shared.SOURCE_LIST),
                f'-GLOCAL_W={local}',f'-GGLOBAL_W={glob}'],build/'lint.log')
    shared.run([shared.VERILATOR,'--binary','--timing','-j','4',*flags,
                '-Wno-WIDTH','-Wno-TIMESCALEMOD','-Wno-INITIALDLY',
                f'-DDP_MIXED_TOP={top}','-DDP_MIXED_GROUPS=4','-DDP_LOWP_FRONTEND',
                '-DDP_E_FRONTEND' if profile=='e64' else '-DDP_QE_FRONTEND',
                '--top-module','dp_tb','--Mdir',str(build),
                f'-GLOCAL_W={local}',f'-GGLOBAL_W={glob}',
                '-I'+str(shared.EXPORT/'src/src/verilog/parameter'),
                '-I'+str(ROOT/'test/rtl_tb'),'-f',str(shared.SOURCE_LIST),
                str(ROOT/'test/rtl_tb/dp_mixed_tb.v')],build/'compile.log')
    return build/'Vdp_tb'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend',choices=LOWP_PROFILES,required=True)
    parser.add_argument('--verilator',default=os.environ.get('VERILATOR','verilator'))
    args=parser.parse_args()
    started=datetime.now(timezone.utc).isoformat()
    shared.FRONTEND=args.frontend
    shared.VERILATOR=args.verilator
    shared.RUN=ROOT/'test/runs/verilog'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    shared.RUN.mkdir(parents=True)
    shared.EXPORT,shared.SOURCE_LIST=snapshot('verilog',args.frontend)
    records=[]
    minimum=7 if args.frontend=='e64' else 3
    modes=[mode for mode,datatype in DTYPES.items() if minimum<=datatype<=9]
    print(f'{args.frontend}: four groups + C, L8/II=1, windows 28/40',flush=True)
    exe=compile_tb(args.frontend,28,40)
    for mode in modes:
        inp=next((ROOT/'test/data/dp'/mode).glob('*/*/inputs.txt'))
        k,requests=read_inputs(inp)
        if k!=16 or len(requests)!=961: raise AssertionError('wrong native corpus')
        golden=[json.loads(line) for line in inp.with_name('expected.jsonl').read_text().splitlines()]
        expected=evaluate(requests,config={'frontend':args.frontend},run_dir=shared.RUN/'model')
        for result,reference in zip(expected,golden):
            result['exact_fp32_or_int32']=reference['exact_fp32_or_int32']
        records.append(shared.campaign(mode,16,28,40,requests,exe,expected=expected))
        if records[-1]['max_ulp'] is not None and records[-1]['max_ulp']>4:
            raise AssertionError('native corpus exceeds 4 ULP')
    rng=random.Random(20271105)
    requests=[random_request(mode,rng,16) for _ in range(48) for mode in modes]
    requests+=shared.e_directed(16)
    # Every unsupported type is presented between legal transactions.
    for mode,datatype in DTYPES.items():
        if not minimum<=datatype<=9:
            requests.extend([make('nvfp4'),make(mode),make('hif4')])
    for update in [dict(b_datatype=2),dict(a_datatype=15,b_datatype=15),dict(c_datatype=1),
                   dict(a_scale_datatype=3),dict(b_scale_datatype=1)]:
        bad=make('nvfp4');bad.update(update);requests.extend([make('hif4'),bad,make('nvfp4')])
    for index,request in enumerate(requests):request.update(id=index,last=index%7==0)
    for k,local,glob in MIXED_CONFIGS:
        records.append(shared.campaign(f'mixed-k{k}-l{local}-g{glob}',k,local,glob,requests,
            exe if (local,glob)==(28,40) else compile_tb(args.frontend,local,glob),stress=True))
    fingerprint=hashlib.sha256(Path(__file__).read_bytes()+(ROOT/'test/rtl_tb/dp_mixed_tb.v').read_bytes()).hexdigest()
    record_validation(shared.EXPORT,records,fingerprint,phase='all',started=started,run_dir=shared.RUN,
                      backend_scope=True,command=[sys.executable,*sys.argv],
                      simulator_version=subprocess.check_output([args.verilator,'--version'],text=True).strip())
    summary=shared.RUN/'verilator-verilog-all-summary.json'
    summary.write_text(json.dumps(records,indent=2)+'\n')
    print(f'Report: {summary.relative_to(ROOT)}',flush=True)

if __name__=='__main__':main()
