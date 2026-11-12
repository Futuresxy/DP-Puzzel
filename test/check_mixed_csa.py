#!/usr/bin/env python3
"""Supplemental mixed CSA tests against an explicit frozen RTL snapshot."""
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-id', required=True)
    parser.add_argument('--iverilog', default='iverilog')
    parser.add_argument('--vvp', default='vvp')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    export = ROOT/'hw/rtl'/args.export_id
    _, fingerprint, _ = payload(export, ROOT)
    files = [export/'src/src/verilog/arithmetic'/name for name in
             ('dp_csa_3to2.v', 'dp_csa_4to2.v', 'dp_mixed_csa_sum.v')]
    bench = ROOT/'test/rtl_tb/dp_mixed_csa_tb.v'
    checks = []
    with tempfile.TemporaryDirectory(prefix='dp-mixed-csa-') as work:
        for width in (3, 40, 64):
            for extension_count in (2, 4, 8, 12):
                exe = Path(work)/f'mixed-{width}-{extension_count}.vvp'
                subprocess.run([args.iverilog, '-g2005', '-s', 'dp_mixed_csa_tb',
                                f'-Pdp_mixed_csa_tb.W={width}',
                                f'-Pdp_mixed_csa_tb.EXT_GROUPS={extension_count}',
                                '-o', str(exe), *map(str, files), str(bench)], check=True)
                output = subprocess.check_output([args.vvp, str(exe)], text=True).strip()
                if not output.startswith('PASS '):
                    raise AssertionError(output)
                print(output, flush=True)
                checks.append(output)
    result = dict(export_id=args.export_id, rtl_fingerprint=fingerprint, checks=checks,
                  bench_sha256=hashlib.sha256(bench.read_bytes()).hexdigest(),
                  runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  tool=subprocess.check_output([args.iverilog, '-V'], text=True,
                                               stderr=subprocess.DEVNULL).splitlines()[0])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
