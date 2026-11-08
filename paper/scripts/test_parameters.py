"""Exercise changed core budget, DP costs, batch and context without touching paper outputs."""
import copy
import json
from pathlib import Path
import tempfile
import csv
import reproduce
ROOT=Path(__file__).resolve().parents[1]
base=json.loads((ROOT/'data/inputs/experiment.json').read_text())
hw=json.loads((ROOT/'data/inputs/hardware_n12.json').read_text())
with tempfile.TemporaryDirectory(prefix='dp-paper-parameters-') as tmp:
    root=Path(tmp)
    config=copy.deepcopy(base)
    config.update(baseline_cores=32,contexts=[2048],batch=2,simplex_divisions=10)
    config['hardware']='hardware.json'
    (root/'hardware.json').write_text(json.dumps(hw))
    cfgpath=root/'experiment.json'; cfgpath.write_text(json.dumps(config))
    reproduce.run(cfgpath,root/'cores32')
    result=json.loads((root/'cores32/data/results/manifest.json').read_text())
    assert result['integer_cores']==[32,29,28,26]
    assert result['model_points']==6
    with (root/'cores32/data/results/prefill_points.csv').open() as f: points=list(csv.DictReader(f))
    for p in points:
        f,_,_=reproduce.mapped_work(p['model'],'prefill',2048,'reference_work',1)
        assert int(p['total_hqe_flops'])==int(2*f.sum())
    config.update(baseline_cores=36,tensor_area_fraction=.4,array_m=8,contexts=[2048,8192])
    # A deliberate sensitivity scenario, not a new hardware measurement.
    hw['designs'][1]['area_um2']=hw['designs'][0]['area_um2']
    hw['designs'][1]['power']['mxfp4_e2m1']['total_mw'] *= .5
    (root/'hardware.json').write_text(json.dumps(hw));cfgpath.write_text(json.dumps(config))
    reproduce.run(cfgpath,root/'changed_costs')
    result=json.loads((root/'changed_costs/data/results/manifest.json').read_text())
    assert result['integer_cores'][:2]==[36,36]
    assert abs(result['area_budget_mm2']-405.5663803392*.5*.3/.4)<1e-10
    regions=json.loads((root/'changed_costs/data/results/energy_encoding_regions.json').read_text())
    assert regions['mx_only'][1]['fraction']>0  # Previously absent region now has a winner.
print('PASS: changed core budget, array size, area fraction, hardware area/power, batch and short context lists')
