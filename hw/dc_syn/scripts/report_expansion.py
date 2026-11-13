#!/usr/bin/env python3
"""Audit explicitly selected new DP synthesis runs without replacing old records."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from run_dc import ROOT, run_path
from report_dc import analyze
from latest_synthesis import record

PROFILES = {
    'dp_top_t8h16q96e192': ('dp_top_t8h16q96e192', 'T8H16Q96E192', 't8h16q96e192', 96, 192),
    'dp_top_t8h16q128e256': ('dp_top_t8h16q128e256', 'T8H16Q128E256', 't8h16q128e256', 128, 256),
    'dp_top_t8h16q64e64': ('dp_top_t8h16q64e64', 'T8H16Q64E64', 't8h16q64e64', 64, 64),
    'dp_top_t8h16q32e192': ('dp_top_t8h16q32e192', 'T8H16Q32E192', 't8h16q32e192', 32, 192),
    'dp_top_t8h16q32e256': ('dp_top_t8h16q32e256', 'T8H16Q32E256', 't8h16q32e256', 32, 256),
}


def collect(run_ids):
    records = []
    common = None
    tops = set()
    for run_id in run_ids:
        run = run_path(run_id)
        data = json.loads((run / 'inputs/resolved.json').read_text())
        state = json.loads((run / 'state.json').read_text())
        measured = analyze(run, data)
        top = data['gate']['top']
        if top not in PROFILES or top in tops:
            raise ValueError('Unknown or repeated expansion top: ' + top)
        if state['phase'] != 'finished' or not measured['flow_pass']:
            raise ValueError('Synthesis has not passed all acceptance checks: ' + run_id)
        condition = {name: data[name] for name in ('technology', 'target_dbs')}
        # Compare every electrical/timing/compile budget; report hierarchy separately.
        condition['constraints'] = {key: value for key, value in data['constraints'].items()
                                    if key not in ('constraint_id', 'purpose', 'hierarchy')}
        condition.update(parameters=data['gate']['parameters'], dc_version=measured['dc_version'])
        if (data['technology']['technology_id'] != 'n12-bwp6t-120a-base-lvt-tt-0p7v-85c'
                or data['technology']['pvt'] != dict(corner='TT', voltage_v=0.7, temperature_c=85)
                or data['constraints']['period_ns'] != 1
                or not data['constraints']['clock_gating']):
            raise ValueError('Unexpected synthesis condition')
        if common is not None and common != condition:
            raise ValueError('Selected runs use different synthesis conditions')
        common = condition
        tops.add(top)
        entry = record(run, data, measured, PROFILES[top])
        entry['synthesis_strategy'] = {key: data['constraints'][key]
                                       for key in ('constraint_id', 'purpose', 'hierarchy')}
        records.append(entry)
    if not records:
        raise ValueError('An explicit completed run is required')
    # Actual library bindings remain in ignored resolved.json, not published.
    published_condition = {key: value for key, value in common.items() if key != 'target_dbs'}
    return dict(schema_version=1, status='PASS', audited_utc=datetime.now(timezone.utc).isoformat(),
                scope='explicit passing frozen runs; synthesis only, pre-CTS/pre-route',
                condition=published_condition, records=records)


def publish(result, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    fields = ['top', 'capacity', 'run', 'export_id', 'verification_id', 'area_um2',
              'setup_ps', 'hold_ps', 'icg', 'gated_registers', 'total_registers']
    fields += [f'S{stage}_setup_ps' for stage in range(1, 9)]
    rows = []
    for entry in result['records']:
        measured = entry['result']
        gating = entry['clock_gating_measurement']
        row = {key: entry[key] for key in fields[:5]}
        row.update(area_um2=measured['total_area_um2'], setup_ps=1000*measured['setup_slack_ns'],
                   hold_ps=1000*measured['hold_slack_ns'], icg=gating['gating_elements'],
                   gated_registers=gating['gated_registers'], total_registers=gating['total_registers'])
        row.update({f'S{stage}_setup_ps': 1000*entry['stage_setup_paths'][f'S{stage}']['slack_ns']
                    for stage in range(1, 9)})
        rows.append(row)
    with output.with_suffix('.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# 扩展 DP 的 N12 / 1 GHz 综合验收', '',
             '工况：N12 BWP6T16P96CPD 120a、TT/0.7V/85°C、base+LVT≤20%、ICG、L8/II=1，LOCAL28/GLOBAL40。',
             '所有所选运行的库、工具版本、时钟/IO、电气及编译预算均逐项一致；setup/hold、电气及VT全部通过。层级展开策略按架构记录，面积差异包含该策略影响。',
             '结果为 ZeroWireload、理想时钟下的综合后证据，不是 CTS/布线后签核。极小正裕量只表示本工况通过。', '',
             '| 架构 | 面积 µm² | setup ps | hold ps | ICG | 门控寄存器 |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in rows:
        lines.append(f"| {row['capacity']} | {row['area_um2']:.6f} | {row['setup_ps']:.6f} | "
                     f"{row['hold_ps']:.6f} | {row['icg']} | {row['gated_registers']}/{row['total_registers']} |")
    lines += ['', '## 捕获级 setup 裕量（ps）', '',
              '| 架构 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in rows:
        lines.append('| ' + row['capacity'] + ' | ' + ' | '.join(
            f"{row[f'S{stage}_setup_ps']:.6f}" for stage in range(1, 9)) + ' |')
    lines += ['', '每列按捕获寄存器归属统计，不假定路径一定起自相邻前级；起止点见JSON及原始报告。', '',
              '## 冻结来源', '']
    for row in rows:
        lines.append(f"- `{row['capacity']}`：[{Path(row['run']).name}](../runs/{Path(row['run']).name}/REPORT.md)；"
                     f"RTL `{row['export_id']}`；原始验证 `{row['verification_id']}`。")
    lines += ['', '## 层级优化策略', '']
    for entry in result['records']:
        strategy = entry['synthesis_strategy']
        lines.append(f"- `{entry['capacity']}`：`{strategy['constraint_id']}`；展开模块："
                     + ', '.join(f'`{name}`' for name in strategy['hierarchy']['expand_modules']) + '。')
    lines += ['', '各run保存原始日志、约束、DDC、网表和SDC；修复使用新run并保持完整来源链。',
              '功耗使用相同网表，但须另经真实负载 RTL/门级重放、原生 SAIF 及活动审计；本表不代表功耗通过。', '']
    output.with_suffix('.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    publish(collect(args.run_id), args.output)
