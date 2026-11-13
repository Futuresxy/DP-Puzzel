"""Calculate the predeclared paired contrasts from a verified MoE summary."""
import argparse
from pathlib import Path

from ratio_dse.common import digest, require
from .characterize import write_json
from .summarize_system import read_rows


def findings(summary, output):
    rows=read_rows(summary/'primary_cells.csv')
    trace=read_rows(summary/'primary_operator_breakdown.csv')
    def cell(plan,ratio,regime='fixed',cap=''):
        matches=[r for r in rows if (r['plan'],r['ratio'],r['regime'],r['cap_w'])==(plan,ratio,regime,cap)]
        require(len(matches)==1 and matches[0]['seconds'],'required comparison unavailable')
        return matches[0]
    def compare(a,b):
        return {'from_candidate':a['candidate_id'],'to_candidate':b['candidate_id'],
                'from_seconds':float(a['seconds']),'to_seconds':float(b['seconds']),
                'latency_reduction_fraction':1-float(b['seconds'])/float(a['seconds'])}
    def stages(row,prefix):
        names={'shared':('shared_gate','shared_up','shared_down'),
               'routed':('expert_gate','expert_up','expert_down'),
               'communication':('dispatch','combine')}[prefix]
        return sum(float(r['seconds']) for r in trace if r['candidate_id']==row['candidate_id'] and r['name'] in names)
    baseline=cell('routed_nvfp4','1:2:4')
    expanded=cell('routed_nvfp4','1:2:16')
    optimized=cell('routed_nvfp4','1:2:4','optimized')
    changed=cell('routed_nvfp4','1:6:12','optimized')
    total_saved=float(optimized['seconds'])-float(changed['seconds'])
    shared_saved=stages(optimized,'shared')-stages(changed,'shared')
    near_best=[]
    for cap in ('','250'):
        for plan in ('w4a8','routed_mxfp4','routed_nvfp4'):
            feasible=[r for r in rows if r['regime']=='optimized' and r['cap_w']==cap and r['plan']==plan and r['seconds']]
            best=min(feasible,key=lambda r:float(r['seconds']))
            near_best.append({'plan':plan,'cap_w':cap or None,'best_candidate':best['candidate_id'],
                'best_ratio':best['ratio'],'seconds':float(best['seconds']),
                'design':{k:best[k] for k in ('physical_sms','enabled_sms','vector_scale','hbm_id','l2_id')},
                'ratios_within_one_percent_latency':[r['ratio'] for r in feasible if float(r['seconds'])<=float(best['seconds'])*1.01]})
    data={'scope':'analytical one-MoE-sublayer contrasts; quality unknown; power uncalibrated',
          'fp4_peak_expansion_at_fixed_system':compare(baseline,expanded),
          'baseline_resource_reallocation':compare(baseline,optimized),
          'ratio_change_after_both_systems_optimize':compare(optimized,changed),
          'combined_change_not_attributable_to_ratio_alone':compare(baseline,changed),
          'remaining_fp8_shared_gemm':{'from_candidate':optimized['candidate_id'],'to_candidate':changed['candidate_id'],
              'total_saved_s':total_saved,'shared_gemm_saved_s':shared_saved,
              'shared_fraction_of_savings':shared_saved/total_saved,
              'routed_gemm_saved_s':stages(optimized,'routed')-stages(changed,'routed'),
              'communication_fraction_after':stages(changed,'communication')/float(changed['seconds'])},
          'cost_only_winners_and_near_ties':near_best,
          'inputs_sha256':{name:digest(summary/name) for name in ('primary_cells.csv','primary_operator_breakdown.csv')},
          'script_sha256':digest(Path(__file__))}
    write_json(output,data)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    findings(args.summary,args.output)


if __name__=='__main__':main()
