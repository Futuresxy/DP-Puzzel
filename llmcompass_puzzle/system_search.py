"""Paired chip-to-recipe / recipe-to-chip search on a DeepSeek-derived MoE boundary."""
import argparse
from collections import defaultdict
from itertools import product
from pathlib import Path

from ratio_dse.area_model import import_profiles
from ratio_dse.common import ROOT, digest, identity, read_json, require, write_csv
from .backend import LOCK, baseline_config, chip_area
from .characterize import scale_profile, write_json
from .moe_system import make_design, evaluate
from .quality import quality_key, assess_quality


def table(path, rows):
    columns = sorted({key for row in rows for key in row}) or ['status']
    write_csv(path, rows, columns)


def run(config_path, output):
    config_path, output = config_path.resolve(), output.resolve()
    require(not output.exists(), 'output must be new')
    cfg = read_json(config_path)
    study_id = identity('study', cfg)
    area_cfg_path = ROOT/'llmcompass_puzzle/configs/characterize.json'
    area_cfg = read_json(area_cfg_path)
    hardware, evidence = import_profiles(read_json(ROOT/area_cfg['dp_evidence']))
    profiles = [scale_profile(p,area_cfg['process'],area_cfg['common_clock_hz']) for p in hardware['profiles']]
    budget = chip_area(baseline_config())['total_mm2']
    quality_path = ROOT/cfg['quality_policy']
    policy = read_json(quality_path)
    records = read_json(ROOT/cfg['quality_records']) if cfg['quality_records'] else []
    revisions = {x['model']:x['revision'] for x in read_json(ROOT/'paper/data/evidence/model_sources.json')}
    designs, candidates, details, plans = [], [], [], []
    output.mkdir(parents=True)
    for profile,sm,vec,hbm,l2 in product(profiles,cfg['physical_sms'],cfg['vector_scales'],cfg['hbm_bundles'],cfg['l2_bundles']):
        design = make_design(profile,sm,vec,hbm,l2,cfg['settings'])
        design['within_area_budget'] = design['area_mm2'] <= budget
        designs.append(design)
    model_paths=[]
    for model_name in cfg['models']:
        model_path=ROOT/'paper/data/inputs/models'/model_name/'inference/config.json'
        model_paths.append(model_path)
        model=read_json(model_path)
        for plan in cfg['plans']:
            recipe = cfg['numerical_recipes'][plan]
            key=quality_key(revisions[model_name],digest(model_path),
                            {'scope':'all_routed_expert_linears_only','plan':plan,'other_operators':'unchanged',
                             'numerical_recipe': recipe})
            bound = all(isinstance(recipe.get(k),str) and recipe[k] for k in
                        ('quantizer_revision','calibration_sha256','numerical_graph_sha256'))
            quality=(assess_quality(key,policy,records) if bound else
                     {'status':'unknown','admitted':False,'reason':'numerical_recipe_not_bound'})
            plans.append({'model':model_name,'plan':plan,'quality_key':key,'quality_status':quality['status']})
            for tokens,fusion,cap in product(cfg['tokens'],cfg['fusion'],cfg['caps_w']):
                for design in designs:
                    common={'candidate_id':identity('case',[study_id,model_name,plan,tokens,fusion,cap,design['design_id']]),
                            'model':model_name,'plan':plan,'tokens':tokens,'fusion':fusion,'cap_w':cap,
                            'design_id':design['design_id'],'ratio':design['ratio'],'area_mm2':design['area_mm2'],
                            'quality_key':key,'quality_status':quality['status'],
                            'quality_admitted':quality['admitted'],'power_status':'conditional_on_assumed_coefficients'}
                    if not design['within_area_budget']:
                        candidates.append(common|{'status':'area_infeasible'})
                        continue
                    profile=next(p for p in profiles if p['profile_id']==design['profile_id'])
                    result,trace=evaluate(model,tokens,plan,fusion,design,profile,cfg['settings'],cfg['power'],cap)
                    candidates.append(common|result)
                    # Keep all per-stage evidence in the ignored run; small summary only committed.
                    details.extend(common|r for r in trace)
    forward=defaultdict(list);reverse=defaultdict(list)
    for row in candidates:
        if 'seconds' not in row:continue
        forward[tuple(row[k] for k in ('model','plan','tokens','fusion','cap_w'))].append(row)
        reverse[tuple(row[k] for k in ('model','tokens','fusion','cap_w','design_id'))].append(row)
    selections=[];certified=[]
    for direction,groups in [('workload_to_hardware',forward),('hardware_to_migration',reverse)]:
        for group,rows in groups.items():
            best=min(rows,key=lambda x:(x['seconds'],x['candidate_id']))
            selections.append(best|{'direction':direction})
            qualified=[r for r in rows if r['quality_admitted']]
            if qualified:
                certified.append(min(qualified,key=lambda x:x['seconds'])|{'direction':direction})
    comparisons=[]
    for group,rows in forward.items():
        base=[r for r in rows if r['ratio']=='1:2:4']
        if not base:continue
        optimized_baseline=min(base,key=lambda x:x['seconds'])
        best=min(rows,key=lambda x:x['seconds'])
        comparisons.append({**dict(zip(('model','plan','tokens','fusion','cap_w'),group)),
                            'best_candidate':best['candidate_id'],'best_ratio':best['ratio'],
                            'optimized_baseline_candidate':optimized_baseline['candidate_id'],
                            'best_seconds':best['seconds'],'optimized_baseline_seconds':optimized_baseline['seconds'],
                            'gain_over_optimized_baseline':optimized_baseline['seconds']/best['seconds']-1})
    table(output/'designs.csv',designs);table(output/'candidates.csv',candidates)
    table(output/'operator_breakdown.csv',details);table(output/'cost_only_selections.csv',selections)
    table(output/'quality_constrained_selections.csv',certified);table(output/'paired_comparisons.csv',comparisons)
    write_json(output/'quality_bindings.json',plans)
    write_json(output/'config.json',cfg)
    inputs=[config_path,area_cfg_path,ROOT/area_cfg['dp_evidence'],LOCK,quality_path,*evidence,*model_paths,
            ROOT/'paper/data/evidence/model_sources.json',ROOT/'dependencies/quantization_sources.json']
    if cfg['quality_records']:inputs.append(ROOT/cfg['quality_records'])
    sources=[*Path(__file__).parent.glob('*.py'),*ROOT.glob('ratio_dse/area_model/*.py'),ROOT/'ratio_dse/common.py',ROOT/'ratio_dse/formats.py']
    def input_name(path):
        return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    write_json(output/'manifest.json',{'study_id':study_id,'scope':cfg['scope'],'full_model_ttft':False,'budget_mm2':budget,
               'quality_recommendations':len(certified),'power_calibration':'assumed_scenario_only',
               'inputs_sha256':{input_name(p):digest(p) for p in inputs},
               'sources_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sources},
               'outputs_sha256':{p.name:digest(p) for p in output.iterdir()}})
    return {'designs':len(designs),'candidates':len(candidates),'modeled':sum('seconds'in r for r in candidates),
            'quality_recommendations':len(certified),'scope':cfg['scope']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'llmcompass_puzzle/configs/moe_system_study.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(run(args.config,args.output))

if __name__=='__main__':main()
