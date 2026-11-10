"""Preserve frozen workload demand; independently verify updated hardware and costs.

Historical expected files remain immutable. Changed winners, deployment, time and
energy are checked against the current measured input, not the historical PPA.
"""
import csv
import json
import math
from pathlib import Path
from import_dp_measurements import build

ROOT = Path(__file__).resolve().parents[1]
FORMATS = ('bf16', 'mxfp8_e4m3', 'mxfp4_e2m1', 'nvfp4')
FLOP_FIELDS = ('BF16_flops', 'FP8_flops', 'MXFP4_flops', 'NVFP4_flops')
changed_fields = {'fastest', 'least_energy', 'speedup_148', 'energy_saving_148'}
checked = 0


def rows(folder, filename):
    with (ROOT/'data'/folder/filename).open() as handle:
        return list(csv.DictReader(handle))


def close(a, b):
    assert math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12), (a, b)


hardware = json.loads((ROOT/'data/inputs/hardware_n12.json').read_text())
assert hardware == build(), 'Hardware input differs from the cited measured CSV/proxy policy'
config = json.loads((ROOT/'data/inputs/experiment.json').read_text())
dp_count = config['array_m']*config['array_n']
base_array = dp_count*hardware['designs'][0]['area_um2']/1e6
other = base_array*(1/config['tensor_area_fraction']-1)
budget = config['baseline_cores']*(base_array+other)
computed = {}
for h, row in zip(hardware['designs'], rows('results', 'core_counts_compute_power.csv'), strict=True):
    assert row['ratio'] == h['ratio']
    array_area = dp_count*h['area_um2']/1e6
    core_area = array_area+other+config['peripheral_growth']*(array_area-base_array)
    count = math.floor(budget/core_area+1e-12)
    for key, value in {'dp_area_um2':h['area_um2'], 'array_area_mm2':array_area,
                       'core_area_mm2':core_area, 'other_area_mm2':core_area-array_area,
                       'budget_mm2':budget, 'integer_cores':count,
                       'continuous_cores':budget/core_area,
                       'remaining_area_mm2':budget-count*core_area}.items():
        close(row[key], value)
    cap, power = [], []
    for fmt in FORMATS:
        p = h['power'][fmt]
        array_cap = dp_count*2*h['macs_cycle'][fmt]*p['frequency_mhz']/1e6
        array_power = dp_count*p['total_mw']/1000
        for key, value in {'array_tflops':array_cap, 'array_w':array_power,
                           'pool_tflops':count*array_cap, 'pool_w':count*array_power}.items():
            close(row[fmt+'_'+key], value)
        cap.append(count*array_cap)
        power.append(count*array_power)
    computed[h['ratio']] = (cap, power)

for prefix in ('', 'nvfp4_'):
    filename = prefix+'prefill_points.csv'
    historical = rows('expected', filename)
    actual = rows('results', filename)
    for old, current in zip(historical, actual, strict=True):
        for key, value in old.items():
            if key in changed_fields:
                continue
            try:
                float(value)
            except ValueError:
                assert value == current[key], (filename, key)
            else:
                close(value, current[key])
            checked += 1
    evaluations = rows('results', prefix+'prefill_evaluations.csv')
    assert len(evaluations) == len(actual)*len(computed)
    by_point = {p['point_id']:p for p in actual}
    costs = {}
    for row in evaluations:
        point = by_point[row['point_id']]
        cap, power = computed[row['ratio']]
        flops = [float(point[k]) for k in FLOP_FIELDS]
        time = sum(f/(c*1e12) for f,c in zip(flops,cap))
        energy = sum(f*p/(c*1e12) for f,p,c in zip(flops,power,cap))
        close(row['time_s'], time)
        close(row['energy_j'], energy)
        close(row['average_dp_w'], energy/time)
        close(row['effective_tflops'], sum(flops)/time/1e12)
        costs.setdefault(row['point_id'], {})[row['ratio']] = (time, energy)
    for point in actual:
        values = costs[point['point_id']]
        for index, key in enumerate(('fastest', 'least_energy')):
            best = min(v[index] for v in values.values())
            winners = '|'.join(r for r,v in values.items() if math.isclose(v[index],best,rel_tol=1e-10))
            assert winners == point[key], (point['point_id'], key)
        close(point['speedup_148'], values['1:2:4'][0]/values['1:4:8'][0])
        close(point['energy_saving_148'], 1-values['1:4:8'][1]/values['1:2:4'][1])
print(f'PASS: {checked} frozen workload fields unchanged; measured costs, deployment and all 168 evaluations verified')
