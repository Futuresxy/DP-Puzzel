"""Extract predeclared fixed-resource / resource-optimized paired experiments."""
import argparse
from collections import defaultdict
import csv
from pathlib import Path

from ratio_dse.common import digest, read_json, require
from .characterize import write_json
from .system_search import table


def read_rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def summarize(run, output):
    require(not output.exists(),'summary output must be new')
    manifest = read_json(run/'manifest.json')
    for name,sha in manifest['outputs_sha256'].items():
        require(digest(run/name)==sha,f'run output changed: {name}')
    cfg=read_json(run/'config.json')
    baseline=cfg['study_design']['fixed_system']
    primary=cfg['study_design']['primary_case']
    designs={r['design_id']:r for r in read_rows(run/'designs.csv')}
    rows=read_rows(run/'candidates.csv')
    groups=defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in ('model','tokens','fusion','cap_w','plan','ratio'))].append(row)
    cells=[]
    for group, candidates in groups.items():
        fixed=[r for r in candidates if all(str(v)==designs[r['design_id']][k] for k,v in baseline.items())]
        require(len(fixed)==1,'fixed-resource control must occur exactly once')
        feasible=[r for r in candidates if r['seconds']]
        best=min(feasible,key=lambda r:(float(r['seconds']),r['candidate_id'])) if feasible else fixed[0]
        for regime,row in [('fixed',fixed[0]),('optimized',best)]:
            design=designs[row['design_id']]
            cells.append(row | {k:design[k] for k in ('physical_sms','enabled_sms','vector_scale','hbm_id','l2_id')} | {'regime':regime})
    primary_cells=[r for r in cells if all(str(v)==r[k] for k,v in primary.items())]
    # Quantization ablation: same model, design, format, cap, tokens; only legal fusion changes.
    by_id={(r['model'],r['tokens'],r['plan'],r['cap_w'],r['design_id'],r['fusion']):r for r in rows}
    ablations=[]
    for r in primary_cells:
        if not r['seconds']:continue
        key=tuple(r[k] for k in ('model','tokens','plan','cap_w','design_id'))
        unfused=by_id[(*key,'False')]
        if unfused['seconds']:
            ablations.append({'fused_candidate':r['candidate_id'],'unfused_candidate':unfused['candidate_id'],
                              'regime':r['regime'],'ratio':r['ratio'],'plan':r['plan'],'cap_w':r['cap_w'],
                              'fused_seconds':float(r['seconds']),'unfused_seconds':float(unfused['seconds']),
                              'saved_seconds':float(unfused['seconds'])-float(r['seconds'])})
    selected={r['candidate_id'] for r in primary_cells if r['seconds']}
    breakdown=[]
    with (run/'operator_breakdown.csv').open() as stream:
        for r in csv.DictReader(stream):
            if r['candidate_id'] in selected:breakdown.append(r)
    # Broad invariants check actual outputs, not just a successful exit code.
    by_candidate=defaultdict(list)
    for r in breakdown:by_candidate[r['candidate_id']].append(r)
    for row in primary_cells:
        if not row['seconds']:continue
        trace=by_candidate[row['candidate_id']]
        require(abs(sum(float(r['seconds']) for r in trace)-float(row['seconds']))<1e-12,'trace duration mismatch')
    for row in rows:
        if not row['seconds']:continue
        require(float(row['area_mm2'])<=manifest['budget_mm2'],'area violation')
        require(float(row['resident_bytes'])+float(row['working_bytes'])<=float(designs[row['design_id']]['hbm_capacity_bytes']), 'capacity violation')
        if row['cap_w']:
            require(float(row['power_envelope_w_proxy'])<=float(row['cap_w']),'stage cap violation')
        require(float(row['energy_j_proxy_upper_per_rank'])<=float(row['power_envelope_w_proxy'])*float(row['seconds'])+1e-9,'energy/envelope mismatch')
    certified=read_rows(run/'quality_constrained_selections.csv')
    require(all(r['quality_admitted']=='True' and r['quality_status']=='passed' for r in certified),'quality gate bypass')
    output.mkdir(parents=True)
    table(output/'controlled_cells.csv',cells)
    table(output/'primary_cells.csv',primary_cells)
    table(output/'fusion_ablation.csv',ablations)
    table(output/'primary_operator_breakdown.csv',breakdown)
    table(output/'paired_comparisons.csv',read_rows(run/'paired_comparisons.csv'))
    table(output/'workload_to_hardware.csv',[r for r in read_rows(run/'cost_only_selections.csv') if r['direction']=='workload_to_hardware'])
    table(output/'quality_constrained_selections.csv',certified)
    write_json(output/'evidence.json',{
        'run':str(run),'manifest_sha256':digest(run/'manifest.json'),'primary_case':primary,
        'fixed_system':baseline,'designs':len(designs),'candidates':len(rows),
        'modeled':sum(bool(r['seconds']) for r in rows),'quality_recommendations':len(certified),
        'checks':['all modeled area/capacity/power envelopes','energy <= peak envelope * duration',
                  'primary trace duration sums','quality gate admission','all source run output hashes'],
        'script_sha256':digest(Path(__file__)),
        'summary_sha256':{p.name:digest(p) for p in output.iterdir()},
        'scope':manifest['scope'],'power_calibration':manifest['power_calibration']})
    return {'candidates':len(rows),'primary_cells':len(primary_cells),'quality_recommendations':len(certified)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    print(summarize(args.run,args.output))


if __name__=='__main__':main()
