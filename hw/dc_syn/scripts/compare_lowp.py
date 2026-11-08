#!/usr/bin/env python3
"""Compare gated four-group low-precision tops with an archived multiprecision DP."""
import argparse
import json
import re
from run_dc import ROOT, DC, run_path, verify_inputs
from report_dc import analyze, compact_record
from rtl_gate import rtl_fingerprint
from compare_mixed import clock_gating


def hierarchy(run, group_reference):
    rows=[]
    for line in (run/'reports/area_hierarchy.rpt').read_text().splitlines():
        fields=line.split()
        if len(fields)!=7:continue
        try:area=float(fields[1])
        except ValueError:continue
        rows.append((fields[0],fields[6],area))
    groups=[row for row in rows if row[1].startswith(group_reference)]
    if len(groups)!=4:raise ValueError('Expected exactly four frontend groups')
    result={'four_groups':sum(row[2] for row in groups)}
    for name,prefix in [('global_alignment','dp_global_align_'),('fp32_round','dp_fp32_round_'),
                        ('c_unpack','dp_c_unpack_')]:
        selected=[row for row in rows if row[1].startswith(prefix)]
        if len(selected)!=1:raise ValueError('Missing/duplicate backend block: '+name)
        result[name]=selected[0][2]
    tree=[row for row in rows if row[0].endswith('/u_final_sop_tree') or row[0]=='u_final_sop_tree']
    if len(tree)!=1:raise ValueError('Missing final SOP tree')
    result['final_sum_tree']=tree[0][2]
    return result


def collect(ident, top, fresh, group_reference):
    run=run_path(ident)
    state=json.loads((run/'state.json').read_text())
    if state.get('phase') in ('prepared','running') or (run/'.running').exists():
        raise ValueError('Run is active')
    resolved=verify_inputs(run) if fresh else json.loads((run/'inputs/resolved.json').read_text())
    measured=analyze(run,resolved)
    if measured['top']!=top or not measured['synthesis_valid']:
        raise ValueError('Invalid synthesis: '+ident)
    export=ROOT/'hw/rtl'/measured['export_id']
    if rtl_fingerprint(export)!=measured['rtl_fingerprint']:raise ValueError('Snapshot changed')
    evidence=json.loads((ROOT/'test/runs/verilog'/resolved['gate']['verification_id']/'verification.json').read_text())
    if (evidence['export_id']!=measured['export_id'] or
        evidence['rtl_fingerprint']!=measured['rtl_fingerprint'] or evidence['status']!='passed' or
        not evidence['numerical_pass'] or not evidence['protocol_pass']):
        raise ValueError('Original receipt mismatch')
    if set(measured['stage_setup_paths'])!={f'S{i}' for i in range(1,9)}:
        raise ValueError('Missing L8 stage timing')
    if '\tunclassified' in (run/'reports/register_stages.tsv').read_text():
        raise ValueError('Unclassified registers')
    condition={key:resolved[key] for key in ('technology','constraints','target_dbs')}
    condition.update(parameters=measured['parameters'],dc_version=measured['dc_version'])
    record=compact_record(measured)
    record.update(top=top,verification_id=evidence['verification_id'],
                  evidence_scope='fresh_gate' if fresh else 'archived_snapshot_and_original_receipt',
                  clock_gating_measurement=clock_gating(run),hierarchy_area_um2=hierarchy(run,group_reference))
    record['hierarchy_area_um2']['other']=record['result']['total_area_um2']-sum(record['hierarchy_area_um2'].values())
    if record['hierarchy_area_um2']['other'] < -0.01:raise ValueError('Overlapping area accounting')
    return record,condition


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-run',required=True)
    parser.add_argument('--e64-run',required=True)
    parser.add_argument('--q32e64-run',required=True)
    parser.add_argument('--record',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.record):parser.error('invalid record name')
    records=[];common=None
    for ident,top,fresh,group in [(args.baseline_run,'dp_top',False,'dp_group_LOCAL'),
        (args.e64_run,'dp_top_e64',True,'dp_group_e_'),
        (args.q32e64_run,'dp_top_q32e64',True,'dp_group_qe_')]:
        record,condition=collect(ident,top,fresh,group)
        if common is not None and condition!=common:raise ValueError('Mismatched tool/library/constraints/parameters')
        common=condition;records.append(record)
    baseline=records[0]['result']['total_area_um2']
    for record in records:record['area_delta_percent']=100*(record['result']['total_area_um2']/baseline-1)
    destination=DC/'records'/args.record
    destination.with_suffix('.json').write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n')
    lines=['# 四组低精度 DP：N12 / 1GHz 面积与时序','','CModel/spec `2db339d`，RTL/验证 `4045e00`；[架构合同](../../../src/spec/dp/dptop/low-precision-tops.md)，[功能验证](../../../test/results/lowp-tops-v1.7.4.md)。',
        '', '两个新顶层分别使用四个 E/QE group；共用五源浮点后端，L8/II=1、LOCAL28/GLOBAL40。QE 使用 COMPACT_UNPACK=1，E 内部架构保持现状。',
        '', '| 顶层 | 面积 µm² | 相对多精度基线 | setup ps | hold ps | 综合验收 |',
        '| --- | ---: | ---: | ---: | ---: | --- |']
    for rec in records:
        r=rec['result'];lines.append(f"| {rec['top']} | {r['total_area_um2']:.2f} | {rec['area_delta_percent']:+.2f}% | {r['setup_slack_ns']*1000:.6f} | {r['hold_slack_ns']*1000:.6f} | {'PASS' if r['flow_pass'] else 'FAIL'} |")
    lines+=['','## 不重叠的模块面积','','| 顶层 | 四组前端 | 全局对齐 | 最终树 | FP32舍入 | C解包 | 其余控制/寄存/修复 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for rec in records:
        h=rec['hierarchy_area_um2'];lines.append('| '+rec['top']+' | '+' | '.join(f'{h[k]:.2f}' for k in ('four_groups','global_alignment','final_sum_tree','fp32_round','c_unpack','other'))+' |')
    lines+=['','分解使用层次报告的模块总面积，各列不重复包含子模块；other 为总面积扣除上述模块。前端面积包含其内部寄存器与门控；S6–S8寄存器及综合修复可计入other，不能将other解释为纯组合控制。','','## 各捕获级 setup slack（ps）','','| 顶层 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for rec in records:
        lines.append('| '+rec['top']+' | '+' | '.join(f"{rec['stage_setup_paths'][f'S{i}']['slack_ns']*1000:.6f}" for i in range(1,9))+' |')
    lines+=['','每列是该级所有寄存端点的最差路径，起止点/路径逻辑见 JSON 与本地原始报告；不假定所有路径一定来自紧邻前级。',
        '', '## 工况与证据', '', 'TSMC CLN12FFCLL BWP6T16P96CPD，120a；TT/0.7V/85°C，base+LVT≤20%，DC X-2025.06，ZeroWireload，时间ns、面积µm²。1ns周期，setup/hold uncertainty=0.1/0.03ns，IO max/min=0.2/0ns，输出负载0.01pF。',
        '', 'dp-mixed-1000mhz-incremental.json：ICG开启、时序优先、最多两次增量优化，无显式面积恢复；仅展开 DFF 包装，保持计算层次，不 retime、不增加流水、不设置功能 false path。若需独立修复，源run/策略存JSON，最终恢复相同约束。',
        '', '多精度基线为历史保留综合，核验冻结指纹及原始回执；新顶层使用本次新门禁。比较程序严格核对同工具/库/参数/最终约束，不把旧证据伪装为今日 RTL 回归。',
        '', '| 顶层 | DC run | 验证 run | ICG | 门控寄存器 |', '| --- | --- | --- | ---: | ---: |']
    for rec in records:
        ident=rec['run'].split('/')[-1];g=rec['clock_gating_measurement']
        lines.append(f"| {rec['top']} | [{ident}](../runs/{ident}/REPORT.md) | `{rec['verification_id']}` | {g['gating_elements']} | {g['gated_registers']}/{g['total_registers']} ({g['gated_percent']:.2f}%) |")
    lines+=['','PASS 包括setup/hold/电气与VT门禁，不声称达到未定义的功耗预算。没有运行真实负载功耗；门控比例不是功耗测量。预布局TT综合的微小正slack不代表布线后或多corner签核。原始报告、网表、DDC只保留本地run，Git仅保存本摘要、JSON和源码/配置。', '', '复现：', '', '```bash',f'python3.11 hw/dc_syn/scripts/compare_lowp.py --baseline-run {args.baseline_run} --e64-run {args.e64_run} --q32e64-run {args.q32e64_run} --record {args.record}', '```','']
    destination.with_suffix('.md').write_text('\n'.join(lines))
    print(destination.relative_to(ROOT))

if __name__=='__main__':main()
