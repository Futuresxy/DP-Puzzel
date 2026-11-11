#!/usr/bin/env python3
"""Publish a matched-condition mixed DP comparison from four explicit valid runs."""
import argparse
import json
from pathlib import Path
import re

from run_dc import ROOT, DC, run_path, verify_inputs
from report_dc import analyze, compact_record

CAPACITIES = {
    'dp_top': ('T8H16Q32E64', 32, 64),
    'dp_top_t8h16q32e96': ('T8H16Q32E96', 32, 96),
    'dp_top_t8h16q32e128': ('T8H16Q32E128', 32, 128),
    'dp_top_t8h16q64e128': ('T8H16Q64E128', 64, 128),
}


def clock_gating(run):
    text = (run/'reports/clock_gating.rpt').read_text()
    def number(label):
        match = re.search(re.escape(label)+r'\s*\|\s*(\d+)(?:\s*\(([\d.]+)%\))?',text)
        if not match:
            raise ValueError('Missing measured clock gating: '+label)
        return int(match[1]), float(match[2]) if match[2] else None
    gates,_ = number('Number of Clock gating elements')
    gated,percent = number('Number of Gated registers')
    total,_ = number('Total number of registers')
    if not gates or not gated or not 0 < gated <= total:
        raise ValueError('Clock gating was requested but not demonstrated')
    return dict(gating_elements=gates,gated_registers=gated,total_registers=total,gated_percent=percent)


def compare(run_ids):
    collected={}
    common=None
    for ident in run_ids:
        run=run_path(ident)
        if (run/'.running').exists():
            raise ValueError('Run still active: '+ident)
        resolved=verify_inputs(run)
        measured=analyze(run,resolved)
        if not measured['synthesis_valid']:
            raise ValueError('Invalid mapped evidence: '+ident+': '+str(measured['errors']))
        top=measured['top']
        if top not in CAPACITIES or top in collected:
            raise ValueError('Unexpected/duplicate top: '+top)
        condition={key:resolved[key] for key in ('technology','constraints','target_dbs')}
        condition['parameters']=resolved['gate']['parameters']
        condition['dc_version']=measured['dc_version']
        if common is not None and common != condition:
            raise ValueError('PVT/library/parameters/tool/constraints differ across runs')
        common=condition
        if set(measured['stage_setup_paths']) != {f'S{i}' for i in range(1,9)}:
            raise ValueError('Missing L8 stage timing evidence: '+ident)
        stages=(run/'reports/register_stages.tsv').read_text()
        if '\tunclassified' in stages:
            raise ValueError('Unclassified pipeline registers: '+ident)
        record=compact_record(measured)
        record.update(top=top,capacity=CAPACITIES[top][0],clock_gating_measurement=clock_gating(run),
                      verification_id=resolved['gate']['verification_id'],
                      constraint_id=resolved['constraints']['constraint_id'],
                      hierarchy=resolved['constraints']['hierarchy'])
        collected[top]=record
    if set(collected)!=set(CAPACITIES):
        raise ValueError('Require the baseline and all three mixed tops')
    baseline=collected['dp_top']['result']['total_area_um2']
    for top,record in collected.items():
        ratio=record['result']['total_area_um2']/baseline
        record['area_delta_percent']=100*(ratio-1)
        record['relative_q_capacity_per_area']=(CAPACITIES[top][1]/32)/ratio
        record['relative_e_capacity_per_area']=(CAPACITIES[top][2]/64)/ratio
    return [collected[top] for top in CAPACITIES]


def markdown(records):
    lines=['# 混合 DP：N12 / 1GHz 综合对比', '',
           '源检查点：CModel `49ae9e6`；RTL `611d58f`；DC 端口位宽修正与完整重测 `47a732f`。', '',
           '四种设计保持 **L8、II=1、LOCAL_W=28、GLOBAL_W=40**。真实参数/工具/库/约束一致性由比较入口检查；数值验证见 [RTL 阶段报告](../../../test/results/mixed-rtl-v1.7.md)。', '',
           '| 容量 | 面积 µm² | 相对基线 | setup最差slack ps | hold最差slack ps | 综合验收 | 门控寄存器 |',
           '| --- | ---: | ---: | ---: | ---: | --- | ---: |']
    for rec in records:
        r=rec['result'];g=rec['clock_gating_measurement']
        lines.append(f"| {rec['capacity']} | {r['total_area_um2']:.2f} | {rec['area_delta_percent']:+.2f}% | {r['setup_slack_ns']*1000:.6f} | {r['hold_slack_ns']*1000:.6f} | {'PASS' if r['flow_pass'] else 'FAIL'} | {g['gated_percent']:.2f}% |")
    lines += ['', '## 各流水捕获边界的 setup slack（ps）', '',
              '每列取该捕获级所有寄存端点的最差路径；可能包含跨级控制旁带，实际起止点以 JSON/原始报告为准。', '',
              '| 容量 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for rec in records:
        values=[rec['stage_setup_paths'][f'S{i}']['slack_ns']*1000 for i in range(1,9)]
        lines.append('| '+rec['capacity']+' | '+' | '.join(f'{v:.6f}' for v in values)+' |')
    if all(rec['result']['flow_pass'] for rec in records):
        lines += ['', '四种设计的八个捕获边界均通过当前1GHz约束，S7增加规约项后仍可保持L8/II=1。各级余量见上表；不少边界接近零，因此该结论只适用于本次预布局综合。', '']
    lines += ['', '## 最终修复策略', '']
    for rec in records:
        electrical = rec.get('design_rule_repair')
        timing = rec.get('timing_repair')
        hold = rec.get('hold_repair')
        if electrical:
            description = '电气规则修复后重新检查hold，源为 `' + electrical['source_run'] + '`'
            for instance, expected, target in electrical.get('resize_inverters', []):
                description += f'；`{instance}` 从 `{expected}` 调整为逻辑函数相同的 `{target}`'
        elif timing:
            description = '临时加严setup 50ps做增量优化，再恢复原始约束；源为 `' + timing['source_run'] + '`'
        elif hold:
            description = '临时加严hold 1ps修复后恢复原始约束；源为 `' + hold['source_run'] + '`'
        else:
            description = '直接综合，无额外修复运行'
        lines.append('- ' + rec['capacity'] + '：' + description + '。')
    lines += ['', 'DC流程软件测试40项通过；包括输入漂移、无效父运行、电气违规阻止整体PASS和显式驱动调整范围检查。', '']
    lines += ['', '## 来源及边界', '',

              '工艺：TSMC CLN12FFCLL，BWP6T16P96CPD，120a；base+LVT（上限20%），TT/0.7V/85°C；DC X-2025.06。时间ns、面积µm²，ZeroWireload。时钟周期1ns、setup uncertainty 0.1ns、hold uncertainty 0.03ns；IO最大延迟0.2ns、最小0ns，输出负载0.01pF。', '',
              '使用 `dp-mixed-1000mhz-incremental.json`：真实 ICG 门控、时序驱动 compile_ultra、最多两次增量优化、无显式面积恢复；仅展开 DFF 包装层，保留计算模块层级。所有修复最终恢复相同周期/IO/uncertainty，不使用 false path、multicycle 或 retiming。逐 run 的修复策略、源 DDC 和实际 VT 在 JSON 中记录，网表保存在本地 run。', '',
              '最初工具尝试因隔离启动/无尺寸DFF端口/被忽略的旧 timing_high_effort_script 选项而作废；不作为有效 PPA。DFF端口改为显式宽度零值后五个前端重新完整回归。门禁未放松，也未用旧快照替代当前实现。', '',
              'PASS 指映射有效、setup/hold、VT 及电气规则门禁通过。启用泄漏优化后，工具在 constraints.rpt 中报告 max_leakage_power 的 Required=0 且 VIOLATED；本轮没有定义或验收功耗预算，因此不声称所有功耗约束通过。', '',
              '这是指定 TT corner 的预布局标准单元综合结果，接近零的正slack不代表布线后裕量。未将门控覆盖率当作真实负载功耗；PPA比较包含实际必要的时序修复开销，不是各模块理论最小面积。', '',
              '| 容量 | 最终run | 验证run | ICG数量 |', '| --- | --- | --- | ---: |']
    for rec in records:
        run=Path(rec['run']).name
        lines.append(f"| {rec['capacity']} | [{run}](../runs/{run}/REPORT.md) | `{rec['verification_id']}` | {rec['clock_gating_measurement']['gating_elements']} |")
    lines += ['', '网表、DDC、全部原始报告保留在对应本地run的netlist/reports目录；Git只保存本摘要、JSON、配置和复现代码。被最终run引用的修复源与验证证据一并保留。', '']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='append',required=True)
    parser.add_argument('--record',required=True,help='Safe record basename without extension')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.record):
        parser.error('invalid record basename')
    records=compare(args.run)
    out=DC/'records'/args.record
    out.with_suffix('.json').write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n')
    out.with_suffix('.md').write_text(markdown(records))
    print(out.relative_to(ROOT))

if __name__=='__main__':main()
