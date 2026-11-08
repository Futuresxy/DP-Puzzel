#!/usr/bin/env python3
"""Supplement full DP regression with stale-register mode transitions and E boundaries.

Uses the ordinary numerical/cycle/cutpoint testbench and unmodified CModel.
This supplementary receipt does not replace the full RTL-to-PPA gate.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random

import run_verilog as runner
from cases.common import random_request, make
from reference.exact import DTYPES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verilator', default=os.environ.get('VERILATOR', 'verilator'))
    parser.add_argument('--export-id', required=True, help='Frozen RTL from the full regression')
    args = parser.parse_args()
    runner.VERILATOR = args.verilator
    runner.RUN = runner.ROOT / 'test/runs/verilog' / ('precision_gating_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    runner.RUN.mkdir(parents=True)
    runner.EXPORT = runner.ROOT / 'hw/rtl' / args.export_id
    resolved = ['+incdir+' + str(runner.EXPORT / line[len('+incdir+'):]) if line.startswith('+incdir+') else str(runner.EXPORT / line)
                for line in (runner.EXPORT/'files.f').read_text().splitlines()]
    runner.SOURCE_LIST = runner.RUN/'files.f'
    runner.SOURCE_LIST.write_text('\n'.join(resolved)+'\n')
    rng = random.Random(20261108)
    reports = []
    # Each ordered pair of types, dirty payload -> destination, then explicit zeros.
    for local in (27, 28, 32):
        exe = runner.compile_tb(16, local, 40 if local != 32 else 64)
        requests = []
        for first in DTYPES:
            for second in DTYPES:
                for mode in (first, second):
                    requests.append(random_request(mode, rng, 16, len(requests)))
                zero_request = make(second, 16, ident=len(requests))
                zero_request.update(a='0', b='0')
                requests.append(zero_request)
        cfg = dict(frontend='multi', k_fp16=16, local_shift_mag_width=local,
                   global_signed_align_width=40 if local != 32 else 64)
        expected = runner.evaluate(requests, trace=True, config=cfg, run_dir=runner.RUN/'reference')
        for request, result in zip(requests, expected):
            result['exact_fp32_or_int32'] = f'{runner.reference(request, cfg, True)["bits"]:08x}'
        reports.append(runner.campaign('all-mode-pairs-continuous-l'+str(local), 16, local,
                                       cfg['global_signed_align_width'], requests, exe,
                                       expected=expected, observe=True))
        reports.append(runner.campaign('all-mode-pairs-reset-l'+str(local), 16, local,
                                       cfg['global_signed_align_width'], requests, exe,
                                       expected=expected, stress=True))
        # Includes all E raw codes and HiF4 metadata/cancellation boundaries.
        directed = runner.e_directed(16)
        for offset in range(0, len(directed), 1800):
            batch = directed[offset:offset+1800]
            cfg = dict(frontend='multi', k_fp16=16, local_shift_mag_width=local,
                       global_signed_align_width=40 if local != 32 else 64)
            expected = runner.evaluate(batch, trace=True, config=cfg, run_dir=runner.RUN/'reference')
            for request, result in zip(batch, expected):
                result['exact_fp32_or_int32'] = f'{runner.reference(request, cfg, True)["bits"]:08x}'
            reports.append(runner.campaign(f'e-boundaries-l{local}-{offset}', 16, local,
                                           cfg['global_signed_align_width'], batch, exe,
                                           expected=expected, observe=True))
    receipt = dict(status='PASS', export_id=runner.EXPORT.name, seed=20261108, scopes=reports,
                   purpose='supplementary precision gating equivalence; not a replacement PPA gate')
    (runner.RUN/'precision_gating.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(runner.RUN/'precision_gating.json', flush=True)


if __name__ == '__main__':
    main()
