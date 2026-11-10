"""Import measured DP costs and an explicit MXFP4 proxy for NVFP4.

The archived historical hardware input and workload expected files are not modified.
Run from any directory; provenance stays in JSON, outside the manuscript prose.
"""
import copy
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / 'paper'
SOURCE = ROOT / 'hw/power/records/v19_six_architectures_20261110.csv'
DESIGNS = [('1:2:4', 'dp_top'), ('1:2:6', 'dp_top_t8h16q32e96'),
           ('1:2:8', 'dp_top_t8h16q32e128'), ('1:4:8', 'dp_top_t8h16q64e128_opt')]
FORMATS = ('bf16', 'mxfp8_e4m3', 'mxfp4_e2m1')


def build():
    with SOURCE.open() as handle:
        rows = {(r['top'], r['format']): r for r in csv.DictReader(handle)}
    result = dict(process='N12', source=str(SOURCE.relative_to(ROOT)),
                  source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  voltage_v=0.7, temperature_c=85, frequency_mhz=1000,
                  evidence_scope='post_synthesis_pre_CTS_pre_route',
                  source_model='Qwen3-8B layer 0 MLP down_proj',
                  power_assumptions={'nvfp4': 'MXFP4 total power proxy; not measured NVFP4 power',
                                     'bf16': 'BF16 represents H; FP16 power is not measured here'},
                  designs=[])
    for ratio, top in DESIGNS:
        modes = [rows[top, f] for f in FORMATS]
        areas = {float(r['area_um2']) for r in modes}
        assert len(areas) == 1
        design = dict(ratio=ratio, source_tile=top, area_um2=areas.pop(), macs_cycle={}, power={})
        for fmt, row in zip(FORMATS, modes):
            k = int(row['logical_k'])
            power = {key: float(row[key]) for key in
                     ('total_mw', 'internal_mw', 'switching_mw', 'pj_per_mac')}
            power.update(leakage_mw=float(row['static_mw']), frequency_mhz=1000,
                         evidence_status='measured', source_format=fmt,
                         source_report=str(SOURCE.relative_to(ROOT)),
                         dc_run=row['dc_run'], export_id=row['export_id'],
                         verification_id=row['dc_original_verification_id'],
                         workload_receipt=row['workload_receipt'],
                         activity='VCS native gate-level SAIF; 512 ns measurement window')
            assert abs(power['total_mw']/k-power['pj_per_mac']) < 1e-12
            design['macs_cycle'][fmt] = k
            design['power'][fmt] = power
        design['macs_cycle']['nvfp4'] = design['macs_cycle']['mxfp4_e2m1']
        proxy = copy.deepcopy(design['power']['mxfp4_e2m1'])
        proxy.update(evidence_status='proxy_mxfp4',
                     assumption='Same peak MAC/cycle; MXFP4 power used temporarily for NVFP4')
        design['power']['nvfp4'] = proxy
        result['designs'].append(design)
    return result


if __name__ == '__main__':
    destination = PAPER / 'data/inputs/hardware_n12.json'
    destination.write_text(json.dumps(build(), indent=2) + '\n')
    print('Updated four measured DP profiles; NVFP4 explicitly marked as MXFP4 power proxy.')
