"""Compare regenerated default data with the frozen manuscript's numeric results."""
import csv
from pathlib import Path
import math
ROOT=Path(__file__).resolve().parents[1]
checked=0
for filename in ('prefill_points.csv','nvfp4_prefill_points.csv','prefill_evaluations.csv',
                 'nvfp4_prefill_evaluations.csv','core_counts_compute_power.csv'):
    with (ROOT/'data/expected'/filename).open() as f: expected=list(csv.DictReader(f))
    with (ROOT/'data/results'/filename).open() as f: actual=list(csv.DictReader(f))
    assert len(expected)==len(actual),filename
    for a,b in zip(expected,actual):
        for key,value in a.items():
            try:
                x,y=float(value),float(b[key])
            except ValueError:
                assert value==b[key],(filename,key,value,b[key])
            else:
                assert math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-12),(filename,key,x,y)
            checked+=1
print(f'PASS: {checked} fields match the frozen manuscript results')
