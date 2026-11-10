#!/usr/bin/env python3
"""Reproduce the explicitly approximate Ten-Four process comparison, not EDA."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
POWER = ROOT / 'paper/data/DP_area_power/latest6_power.csv'
# User-supplied DeepScaleTool screenshot; target metric = current metric / factor.
SA, SD, SE = 7.273, 1.132, 1.727
# Published rounded Table II values, arXiv:2512.00053v3 (not the older v2).
CONFIGS = [('all_formats', 8, 1.58, 2400., 25.2),
           ('all_formats', 16, 1.58, 4650., 50.4),
           ('mxfp8_only', 8, 1.66, 1060., 26.6),
           ('mxfp8_only', 16, 1.55, 1930., 49.6)]

def main():
    with POWER.open() as stream:
        baseline = next(r for r in csv.DictReader(stream)
                        if r['top'] == 'dp_top' and r['format'] == 'mxfp8_e4m3')
    ours_area_eff = 64. / (float(baseline['area_um2']) / 1.e6) / 1000.
    ours_energy_eff = 64. / float(baseline['total_mw'])
    rows = []
    for variant, kq, freq, area, throughput in CONFIGS:
        native = throughput / (area / 1.e6) / 1000.
        proxy = native / (SA * SD)
        rows.append(dict(variant=variant, q_mac_per_cycle=kq,
                         frequency_7_ghz=freq, area_7_um2=area,
                         throughput_7_gflops=throughput,
                         area_eff_7_tflops_mm2=native,
                         area_proxy14_um2=area*SA,
                         frequency_proxy14_ghz=freq/SD,
                         throughput_proxy14_gflops=throughput/SD,
                         area_eff_proxy14_tflops_mm2=proxy,
                         area_eff_proxy14_fixed_frequency_tflops_mm2=native/SA,
                         ours_over_proxy_area_eff=ours_area_eff/proxy,
                         energy_eff_dp_tflops_w=None))
    result = dict(
        status='analytical_uncalibrated',
        tenfour_source='https://arxiv.org/html/2512.00053v3#S4.T2',
        scaling_method='https://arxiv.org/html/2102.10195v1#S3',
        factors_source='User-supplied DeepScaleTool 14-to-7 nm screenshot; not a new spreadsheet execution',
        factors_14_to_7=dict(area=SA, delay=SD, energy=SE),
        factor_rule='target value = current value / factor',
        reverse_efficiency_rules=dict(area='eta_A7 / (SA * SD)', energy='eta_E7 / SE'),
        assumptions=['14 nm approximates our 12 nm for this comparison only',
                     'Frequency changes inversely with delay; no additional voltage scaling',
                     'No calibration of predictive versus commercial libraries, temperature, utilization or activity'],
        ours=dict(source=str(POWER.relative_to(ROOT)),
                  sha256=hashlib.sha256(POWER.read_bytes()).hexdigest(),
                  area_eff_mxfp8_tflops_mm2=ours_area_eff,
                  energy_eff_mxfp8_tflops_w=ours_energy_eff),
        tenfour_tcu_reported_energy_eff_tflops_w=2.771,
        tenfour_tcu_proxy14_energy_eff_tflops_w=2.771/SE,
        energy_limit='TCU-level reported efficiency only; mode-specific DP power unavailable. Do not use this scalar as a DP efficiency or infer per-mode power from it.',
        rows=rows)
    (HERE / 'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    with (HERE / 'comparison.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    for row in rows:
        print(row['variant'], row['q_mac_per_cycle'],
              'native/proxy area eff = {:.6f}/{:.6f}; ours/proxy = {:.6f}'.format(
                  row['area_eff_7_tflops_mm2'], row['area_eff_proxy14_tflops_mm2'],
                  row['ours_over_proxy_area_eff']))
    print('Ten-Four TCU reported/proxy energy eff:', 2.771, 2.771/SE)

if __name__ == '__main__':
    main()
