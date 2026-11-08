#!/usr/bin/env python3
"""Compare one freshly gated QE optimization against explicit archived DC runs.

Historical snapshots are checked against their frozen directory fingerprints and
original numerical receipts, not relabelled as fresh validations of today's RTL.
"""
import argparse
import json
import re

from run_dc import ROOT, DC, run_path, verify_inputs
from rtl_gate import rtl_fingerprint
from report_dc import analyze, compact_record
from compare_mixed import clock_gating


def hierarchy_areas(run):
    rows = {}
    for line in (run / 'reports/area_hierarchy.rpt').read_text().splitlines():
        fields = line.split()
        if len(fields) != 7:
            continue
        try:
            total, _, comb, seq, _ = map(float, fields[1:6])
        except ValueError:
            continue
        rows[fields[0]] = dict(total=total, comb=comb, seq=seq, reference=fields[6])
    if not rows:
        raise ValueError('Missing hierarchy area rows')
    base = [name for name, row in rows.items() if row['reference'].startswith('dp_group_LOCAL')]
    qe = [name for name, row in rows.items() if row['reference'].startswith('dp_group_qe_')]
    if len(base) != 4 or len(qe) not in (0, 4):
        raise ValueError('Unexpected base/QE instance counts')
    def within_qe(name):
        return any(name == prefix or name.startswith(prefix + '/') for prefix in qe)
    def qe_block(suffix):
        return sum(row['total'] for name, row in rows.items()
                   if within_qe(name) and name.endswith('/' + suffix))
    unpack = [row['total'] for name, row in rows.items() if within_qe(name)
              and row['reference'].startswith(('dp_lane_unpack_QE_ONLY', 'dp_lane_unpack_qe'))]
    if qe and len(unpack) != 8:
        raise ValueError('Expected eight QE unpack instances; do not report missing area as zero')
    return dict(base_groups=sum(rows[name]['total'] for name in base),
                qe_groups=sum(rows[name]['total'] for name in qe),
                global_alignment=sum(row['total'] for row in rows.values()
                                     if row['reference'].startswith(('dp_global_align_', 'dp_mixed_global_align_'))),
                qe_unpack=sum(unpack),
                qe_local_alignment=qe_block('u_local_alignment'),
                qe_product_bank=qe_block('u_product_bank'), qe_lane_tree=qe_block('u_lane_sop_tree'),
                qe_sequential=sum(row['seq'] for name, row in rows.items() if within_qe(name)))


def collect(run_id, expected_top, fresh):
    run = run_path(run_id)
    state = json.loads((run/'state.json').read_text())
    if state.get('phase') in ('running', 'prepared') or (run/'.running').exists():
        raise ValueError('Cannot compare an active run')
    resolved = verify_inputs(run) if fresh else json.loads((run/'inputs/resolved.json').read_text())
    measured = analyze(run, resolved)
    if measured['top'] != expected_top or not measured['synthesis_valid']:
        raise ValueError('Wrong top or invalid synthesis: ' + run_id)
    export = ROOT/'hw/rtl'/measured['export_id']
    if rtl_fingerprint(export) != measured['rtl_fingerprint']:
        raise ValueError('Frozen snapshot fingerprint mismatch')
    receipt = ROOT/'test/runs/verilog'/resolved['gate']['verification_id']/'verification.json'
    evidence = json.loads(receipt.read_text())
    if (evidence['export_id'] != measured['export_id'] or
            evidence['rtl_fingerprint'] != measured['rtl_fingerprint'] or
            evidence['status'] != 'passed' or not evidence['numerical_pass'] or not evidence['protocol_pass']):
        raise ValueError('Original verification receipt mismatch')
    if set(measured['stage_setup_paths']) != {f'S{stage}' for stage in range(1, 9)}:
        raise ValueError('Missing stage timing')
    if '\tunclassified' in (run/'reports/register_stages.tsv').read_text():
        raise ValueError('Unclassified pipeline registers')
    condition = {key: resolved[key] for key in ('technology', 'constraints', 'target_dbs')}
    condition.update(parameters=measured['parameters'], dc_version=measured['dc_version'])
    record = compact_record(measured)
    record.update(top=expected_top, verification_id=evidence['verification_id'],
                  evidence_scope='fresh_gate' if fresh else 'archived_snapshot_and_original_receipt',
                  clock_gating_measurement=clock_gating(run), hierarchy_area_um2=hierarchy_areas(run))
    return record, condition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-run', required=True)
    parser.add_argument('--reference-run', required=True)
    parser.add_argument('--optimized-run', required=True)
    parser.add_argument('--record', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.record):
        parser.error('invalid record basename')
    entries = [('baseline', args.baseline_run, 'dp_top', False),
               ('reference', args.reference_run, 'dp_top_t8h16q64e128', False),
               ('optimized', args.optimized_run, 'dp_top_t8h16q64e128_opt', True)]
    records = {}
    common = None
    for role, run, top, fresh in entries:
        record, condition = collect(run, top, fresh)
        if common is not None and common != condition:
            raise ValueError('Library/PVT/tool/parameters/final constraints differ')
        common = condition
        records[role] = record
    baseline = records['baseline']['result']['total_area_um2']
    reference = records['reference']['result']['total_area_um2']
    optimized = records['optimized']['result']['total_area_um2']
    for record in records.values():
        record['area_delta_percent'] = 100*(record['result']['total_area_um2']/baseline-1)
    result = dict(records=records, saved_vs_reference_um2=reference-optimized,
                  saved_vs_reference_percent=100*(1-optimized/reference),
                  target_65_area_um2=baseline*1.65,
                  excess_over_65_target_um2=max(0, optimized-baseline*1.65),
                  target_65_met=optimized <= baseline*1.65 and records['optimized']['result']['flow_pass'])
    destination = DC/'records'/args.record
    destination.with_suffix('.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    lines = ['# QE 首轮 RTL 面积优化：N12 / 1GHz', '',
             '代码检查点：CModel `2aa89c4`，RTL `db31759`。功能证据见 [v1.7.3 验证](../../../test/results/qe-area-opt-v1.7.3.md)。', '',
             '原始基线和原 QE 为保留的历史综合；核验各自冻结快照、原验证回执及原报告，未伪装成当前源码的新门禁。优化版本使用本轮完整回归与新快照。比较程序核对工艺/库、PVT、工具、参数和最终约束一致。', '',
             '| 设计 | 面积 µm² | 相对基础 DP | setup slack ps | hold slack ps | 综合验收 |',
             '| --- | ---: | ---: | ---: | ---: | --- |']
    for role, record in records.items():
        value = record['result']
        lines.append(f"| {role} | {value['total_area_um2']:.2f} | {record['area_delta_percent']:+.2f}% | {value['setup_slack_ns']*1000:.6f} | {value['hold_slack_ns']*1000:.6f} | {'PASS' if value['flow_pass'] else 'FAIL'} |")
    lines += ['', f"相对原 QE 减少 {reference-optimized:.2f} µm²（{100*(1-optimized/reference):.2f}%）。+65% 面积上限为 {baseline*1.65:.2f} µm²；剩余差距 {max(0,optimized-baseline*1.65):.2f} µm²。目标达成还要求全部时序/电气/VT 验收通过。", '',
              '## 面积分解', '', '| 模块/分类 | 原 QE µm² | 优化 QE µm² | 减少 µm² |', '| --- | ---: | ---: | ---: |']
    for name in records['reference']['hierarchy_area_um2']:
        previous = records['reference']['hierarchy_area_um2'][name]
        current = records['optimized']['hierarchy_area_um2'][name]
        lines.append(f'| {name} | {previous:.2f} | {current:.2f} | {previous-current:.2f} |')
    lines += ['', 'base_groups、qe_groups、global_alignment 互不重叠；qe_unpack/local_alignment/product_bank/lane_tree 是 qe_groups 内部层级，qe_sequential 是其全部本地时序单元面积之和。这些内部/交叉分类不能再次与组面积相加。映射尺寸变化及后端修复均计入总面积，差额不全等于被删除的 RTL 逻辑。', '',
              '## 优化版各捕获级 setup', '', '| 捕获级 | 最差 slack ps | 起点 | 终点 |', '| --- | ---: | --- | --- |']
    for stage, path in records['optimized']['stage_setup_paths'].items():
        lines.append(f"| {stage} | {path['slack_ns']*1000:.6f} | `{path['startpoint']}` | `{path['endpoint']}` |")
    lines += ['', '## 工况与来源', '',
              'TSMC CLN12FFCLL BWP6T16P96CPD，120a；TT/0.7V/85°C，base+LVT 上限20%，DC X-2025.06，ZeroWireload。时间ns、面积µm²。K16/LOCAL28/GLOBAL40，L8/II=1；1ns、setup/hold uncertainty 0.1/0.03ns、IO max/min 0.2/0ns、输出负载0.01pF。', '',
              '使用 dp-mixed-1000mhz-incremental.json，真实 ICG 开启，时序驱动、最多两次增量优化，无显式面积恢复，仅展开 DFF 包装；不使用 false path/multicycle/retiming。若存在修复，JSON 保存源 run 与策略，最终约束不变。门控覆盖率不代表活动功耗；本轮未运行功耗。', '',
              '| 设计 | run | export | ICG | 门控寄存器 |', '| --- | --- | --- | ---: | ---: |']
    for role, record in records.items():
        run = record['run'].split('/')[-1]
        gating = record['clock_gating_measurement']
        lines.append(f"| {role} | [{run}](../runs/{run}/REPORT.md) | `{record['export_id']}` | {gating['gating_elements']} | {gating['gated_percent']:.2f}% |")
    lines += ['', '原始报告、网表和 DDC 保留在本地 runs；这里只提交精简证据。指定 TT corner 的预布局正 slack 不等于布局布线后裕量或多 corner 签核。', '', '复现：', '', '```sh',
              f'python3.11 hw/dc_syn/scripts/compare_qe_area.py --baseline-run {args.baseline_run} --reference-run {args.reference_run} --optimized-run {args.optimized_run} --record {args.record}', '```', '']
    destination.with_suffix('.md').write_text('\n'.join(lines))
    print(json.dumps({key: value for key, value in result.items() if key != 'records'}, indent=2))

if __name__ == '__main__':
    main()
