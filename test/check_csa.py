#!/usr/bin/env python3
"""Supplemental compressor equivalence check against an immutable RTL snapshot."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from dp_rtl_gate import payload


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--export-id', required=True)
    parser.add_argument('--iverilog', default='iverilog')
    parser.add_argument('--vvp', default='vvp')
    parser.add_argument('--report', type=Path, required=True)
    args=parser.parse_args()
    export=ROOT/'hw/rtl'/args.export_id
    _,fingerprint,_=payload(export,ROOT)
    files=[export/'src/src/verilog/arithmetic'/name for name in
           ('dp_csa_3to2.v','dp_csa_4to2.v','dp_final_csa_sum.v')]
    bench=ROOT/'test/rtl_tb/dp_csa_tb.v'
    rows=[]
    with tempfile.TemporaryDirectory(prefix='dp-csa-') as work:
        for width in (3,40,64):
            for count in (2,3,5):
                exe=Path(work)/f'csa-{width}-{count}.vvp'
                subprocess.run([args.iverilog,'-g2005','-s','dp_csa_tb',f'-Pdp_csa_tb.W={width}',
                                f'-Pdp_csa_tb.N={count}','-o',str(exe),*map(str,files),str(bench)],check=True)
                output=subprocess.check_output([args.vvp,str(exe)],text=True).strip()
                if not output.startswith('PASS '): raise AssertionError(output)
                print(output)
                rows.append(output)
    report=dict(export_id=args.export_id,rtl_fingerprint=fingerprint,checks=rows,
                bench_sha256=hashlib.sha256(bench.read_bytes()).hexdigest(),
                runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                tool=subprocess.check_output([args.iverilog,'-V'],stderr=subprocess.DEVNULL,text=True).splitlines()[0])
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__': main()
