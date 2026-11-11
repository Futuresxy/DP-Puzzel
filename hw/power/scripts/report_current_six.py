#!/usr/bin/env python3
"""Audit and publish the six current DP architectures from explicit measured points.

A collection may reuse unchanged measurements; it is not a new simulation run.
Every point must match the current DC catalog and retain its original evidence.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from dp_power_gate import verify_workload_replay
from report_power import FIELDS

MODES = ('bf16', 'mxfp8_e4m3', 'mxfp4_e2m1')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(name):
    path = (ROOT / name).resolve()
    if ROOT not in path.parents:
        raise ValueError('Evidence path outside project')
    return path


def compare_workloads(old_point, new_point):
    """Permit a new CModel answer only when stimuli and exact math are identical."""
    identities = []
    for point in (old_point, new_point):
        directory = contained(point['dataset_directory'])
        if digest(directory / 'manifest.json') != point['dataset_manifest_sha256']:
            raise ValueError('Comparison dataset manifest changed')
        for name, expected in point['dataset_files_sha256'].items():
            if digest(directory / name) != expected:
                raise ValueError('Comparison dataset artifact changed')
        stimuli = {name: value for name, value in point['dataset_files_sha256'].items()
                   if name != 'expected.jsonl'}
        if not stimuli or 'source_reference.jsonl' not in stimuli:
            raise ValueError('Comparison needs source workload identity')
        rows = [json.loads(line) for line in (directory / 'expected.jsonl').read_text().splitlines()]
        exact = [(row['id'], row['last'], row['exact_fp32_or_int32'], row['exact_value']) for row in rows]
        if len(exact) != 1024 or len({row[0] for row in exact}) != 1024:
            raise ValueError('Comparison needs 1024 unique exact references')
        identities.append((stimuli, exact))
    if identities[0] != identities[1]:
        raise ValueError('Comparison workload or exact mathematical reference differs')


def generate(selection, output):
    collection = read(selection)
    retirement_name = collection.get('retirement_receipt')
    retirement = {}
    if retirement_name:
        retirement = read(contained(retirement_name))
        if retirement['schema_version'] != 1:
            raise ValueError('Unknown dependency retirement receipt version')
    catalog_path = contained(collection['dc_catalog'])
    catalog = read(catalog_path)
    architectures = {row['top']: row for row in catalog['records']}
    if len(architectures) != 6:
        raise ValueError('Exactly six DC architectures are required')
    expected = {(top, mode) for top in architectures for mode in MODES
                if (top != 'dp_top_e64' or mode == 'mxfp4_e2m1')
                and (top != 'dp_top_q32e64' or mode != 'bf16')}
    actual = [(p['top'], p['format']) for p in collection['points']]
    if len(actual) != 15 or len(set(actual)) != 15 or set(actual) != expected:
        raise ValueError('Missing, duplicate or unsupported power point')
    results = []
    common = None
    for entry in collection['points']:
        campaign = contained(entry['campaign'])
        directory = campaign / (entry['top'] + '__' + entry['format'])
        state = read(campaign / 'state.json')
        if state['status'] != 'completed':
            raise ValueError('Power campaign did not complete')
        manifest = read(campaign / 'manifest.json')
        if digest(campaign / 'plan.json') != manifest['plan_sha256']:
            raise ValueError('Campaign plan changed')
        for name, sha in manifest['flow_sources_sha256'].items():
            if digest(campaign / 'provenance' / name) != sha:
                raise ValueError('Archived flow changed')
        point = read(directory / 'point.json')
        if point not in read(campaign / 'plan.json')['points']:
            raise ValueError('Point missing from original plan')
        audit_path = directory / 'power_audit.json'
        result = read(audit_path)
        dc = architectures[entry['top']]
        for source in (point, result):
            if (source['top'], source['format']) != (entry['top'], entry['format']):
                raise ValueError('Point identity mismatch')
            if source['dc_run'] != dc['run'] or source['export_id'] != dc['export_id']:
                raise ValueError('Power does not use current DC netlist')
        if result['status'] != 'PASS' or result['area_um2'] != dc['result']['total_area_um2']:
            raise ValueError('Unaccepted point or inconsistent area')
        for name, sha in result['artifacts_sha256'].items():
            if digest(contained(name)) != sha:
                raise ValueError('Power artifact changed: ' + name)
        retained_name = retirement.get('retained_datasets', {}).get(point['dataset_directory'])
        retained_dataset = contained(retained_name) if retained_name else None
        if retained_dataset is not None and directory not in retained_dataset.parents:
            raise ValueError('Retained dataset must be inside its measured point directory')
        dataset = retained_dataset if retained_dataset is not None else contained(point['dataset_directory'])
        if digest(dataset / 'manifest.json') != point['dataset_manifest_sha256']:
            raise ValueError('Dataset manifest changed')
        for name, sha in point['dataset_files_sha256'].items():
            if digest(dataset / name) != sha:
                raise ValueError('Dataset changed')
        receipt = ROOT / 'test/runs/power' / campaign.name / directory.name / 'verification.json'
        verify_workload_replay(ROOT, point, receipt,
                               retired_repair=retirement.get('repairs', {}).get(point['dc_run']),
                               retained_dataset=retained_dataset)
        condition = dict(technology=result['technology'], frequency_hz=result['frequency_hz'],
                         duration_ns=result['duration_ns'], clock_slew_ns=result['clock_slew_ns'],
                         window=read(campaign / 'plan.json')['measurement_window'])
        if common is not None and common != condition:
            raise ValueError('Mixed measurement conditions')
        common = condition
        result.update(audit_path=str(audit_path.relative_to(ROOT)), audit_sha256=digest(audit_path),
                      campaign=entry['campaign'], reused=entry.get('reused', False),
                      workload_receipt=str(receipt.relative_to(ROOT)), workload_receipt_sha256=digest(receipt),
                      original_verification_id=point['original_verification_id'],
                      dc_original_verification_id=read(contained(point['dc_run']) / 'inputs/resolved.json')['gate']['verification_id'],
                      cmodel_config=point.get('cmodel_config', {}), reference_model=point.get('reference_model'))
        results.append(result)
    comparisons = []
    baseline_selection = collection.get('comparison_selection')
    comparison_points = {}
    if baseline_selection:
        comparison = read(contained(baseline_selection))
        comparison_points = {(p['top'], p['format']): p for p in comparison['points']}
        if len(comparison_points) != len(comparison['points']) or set(comparison_points) != expected:
            raise ValueError('Comparison selection must contain the same 15 supported points')
    for result in (results if baseline_selection or collection.get('comparison_baseline') else []):
        baseline_campaign = contained(comparison_points[(result['top'], result['format'])]['campaign']
                                      if baseline_selection else collection['comparison_baseline'])
        if read(baseline_campaign / 'state.json')['status'] != 'completed':
            raise ValueError('Comparison baseline is incomplete')
        name = result['top'] + '__' + result['format']
        directory = baseline_campaign / name
        old = read(directory / 'power_audit.json')
        old_point = read(directory / 'point.json')
        new_point = read(contained(result['campaign']) / name / 'point.json')
        if old['status'] != 'PASS':
            raise ValueError('Unaccepted baseline workload')
        if baseline_selection:
            compare_workloads(old_point, new_point)
        elif old_point['dataset_files_sha256'] != new_point['dataset_files_sha256']:
            raise ValueError('Unaccepted or mismatched baseline workload')
        for field in ('top', 'format', 'logical_k', 'technology', 'frequency_hz', 'duration_ns', 'clock_slew_ns'):
            if old[field] != result[field]:
                raise ValueError('Baseline comparison conditions differ: ' + field)
        for name, sha in old['artifacts_sha256'].items():
            if digest(contained(name)) != sha:
                raise ValueError('Baseline evidence changed')
        receipt = ROOT / 'test/runs/power' / baseline_campaign.name / directory.name / 'verification.json'
        verify_workload_replay(ROOT, old_point, receipt)
        old_dc_verification = read(contained(old_point['dc_run']) / 'inputs/resolved.json')['gate']['verification_id']
        comparisons.append(dict(top=result['top'], format=result['format'],
                                baseline={key: old[key] for key in FIELDS},
                                baseline_audit=str((directory / 'power_audit.json').relative_to(ROOT)),
                                baseline_audit_sha256=digest(directory / 'power_audit.json'),
                                baseline_dc_original_verification_id=old_dc_verification,
                                baseline_point_verification_id=old_point['original_verification_id'],
                                area_change_percent=100*(result['area_um2']/old['area_um2']-1),
                                dynamic_change_percent=100*(result['dynamic_mw']/old['dynamic_mw']-1),
                                total_change_percent=100*(result['total_mw']/old['total_mw']-1)))
    summary = dict(schema_version=1, status='PASS', created_utc=datetime.now(timezone.utc).isoformat(),
                   scope='collection of verified current measurements, not a new 15-point campaign',
                   selection=str(selection.relative_to(ROOT)), selection_sha256=digest(selection),
                   dc_catalog=collection['dc_catalog'], dc_catalog_sha256=digest(catalog_path),
                   condition=common, architectures=catalog['records'], results=results,
                   comparison_baseline=collection.get('comparison_baseline'),
                   comparison_selection=baseline_selection,
                   comparison_selection_sha256=digest(contained(baseline_selection)) if baseline_selection else None,
                   comparisons=comparisons)
    if retirement_name:
        summary.update(retirement_receipt=retirement_name,
                       retirement_receipt_sha256=digest(contained(retirement_name)))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    with output.with_suffix('.csv').open('w') as stream:
        columns = FIELDS + (['dc_run', 'export_id', 'dc_original_verification_id', 'original_verification_id', 'campaign', 'workload_receipt']
                            if collection.get('include_provenance_columns') else [])
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(results)
    labels = collection.get('report', {})
    lines = ['# ' + labels.get('title', '六种 DP 精度门控后面积与真实负载功耗'), '',
             labels.get('architecture_description', '五种复用架构使用当前精度寄存器门控实现；E64保持原专用E前端。') + ' L8/II=1、LOCAL28/GLOBAL40，N12 TT/0.7V/85°C、1GHz、ICG开启。',
             'DC X-2025.06；VCS native gate-level SAIF + Power Compiler。Qwen3-8B第0层MLP down_proj同源1024笔独立输入，测量发射256..767的512ns窗口。',
             labels.get('collection_description', '本表合并明确选定的已测点：三种混合架构本轮新测；dp_top、Q32E64复用已完成门控版测量，E64复用原结果。不是声称重跑了全部15点。'), '',
             '| 架构 | 面积 µm² | 相对dp_top | setup ps | hold ps | 1GHz |',
             '| --- | ---: | ---: | ---: | ---: | --- |']
    for dc in catalog['records']:
        r = dc['result']
        lines.append(f"| {dc['capacity']} | {r['total_area_um2']:.3f} | {dc['area_delta_percent']:+.2f}% | {r['setup_slack_ns']*1000:.6f} | {r['hold_slack_ns']*1000:.6f} | PASS |")
    lines += ['', '动态=Internal+Switching；静态=Leakage。单位mW；总功耗保留工具值，分项相加可能有末位舍入差。', '',
              '| 架构 | 精度 | K | 动态 mW | 静态 mW | 总功耗 mW | pJ/MAC |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in results:
        lines.append(f"| {architectures[row['top']]['capacity']} | {row['format']} | {row['logical_k']} | {row['dynamic_mw']:.6f} | {row['static_mw']:.6f} | {row['total_mw']:.6f} | {row['pj_per_mac']:.6f} |")
    if comparisons:
        lines += ['', '## ' + labels.get('comparison_heading', '与原精度寄存器门控前批次比较'), '',
                  labels.get('comparison_description', '旧功耗原始数据及依赖按用户要求全部保留；原有valid门控在两个版本中均开启。差值包含精度寄存器门控、映射及后端时序修复的整体影响，不能当作单个门控单元的独立贡献。'), '',
                  '| 架构 | 精度 | 原动态 mW | 新动态 mW | 动态变化 | 总功耗变化 |',
                  '| --- | --- | ---: | ---: | ---: | ---: |']
        for row, comp in zip(results, comparisons):
            lines.append(f"| {architectures[row['top']]['capacity']} | {row['format']} | {comp['baseline']['dynamic_mw']:.6f} | {row['dynamic_mw']:.6f} | {comp['dynamic_change_percent']:+.2f}% | {comp['total_change_percent']:+.2f}% |")
    receipt_pairs = {(comp['top'], comp['baseline_dc_original_verification_id'],
                      comp['baseline_point_verification_id']) for comp in comparisons
                     if comp['baseline_dc_original_verification_id'] != comp['baseline_point_verification_id']}
    for top, dc_id, point_id in sorted(receipt_pairs):
        lines += ['', f'历史{top}的DC原回执 `{dc_id}` 与功耗点另引的后续回执 `{point_id}` 均保留并独立核验；后续回执不能替代DC锁定的原验证。']
    lines += ['', 'E64不支持BF16/E4M3，Q32E64不支持BF16；这些组合不填零。跨K比较同时看MAC/周期和pJ/MAC，不能仅按整DP功耗排序。', '',
              '| 架构 | 精度 | 零翻转时钟对象 / 总数 | SAIF审计 |',
              '| --- | --- | ---: | --- |']
    for row in results:
        lines.append(f"| {architectures[row['top']]['capacity']} | {row['format']} | {row['inactive_clock_pins']}/{row['clock_pins']} | PASS |")
    lines += ['', '逐点核验：原冻结RTL完整回归、DC时序/VT/电气规则、1024笔及初始化的RTL/门级逐位结果和L8、原生SAIF、真实引脚无X/Z、Nets/Ports/Pins全部显式注释和逐引脚活动。所有引用输入/产物hash重新检查。',
              '时钟对象包括寄存器和门控相关引脚，不等同于关闭寄存器数。极小正slack仅代表指定TT角综合通过，不是多角布线签核。', '',
              '范围：综合后零延迟、CTS/布线前，无SDF/SPEF，不包含真实布线毛刺、SRAM或阵列互连；NVFP4/HiF4未在本轮实测功耗。', '',
              '完整Internal/Switching、DC/原验证/本次采样索引见同名JSON/CSV；DC索引为 `' + collection['dc_catalog'] + '`。',
              '复核：`python3.11 hw/power/scripts/report_current_six.py --selection ' + str(selection.relative_to(ROOT)) + ' --output ' + str(output.relative_to(ROOT)) + '`。历史数值及原始产物是否仍保留，见 records/README.md 和维护回执。', '']
    if retirement_name:
        lines += ['两条修复链使用清理前的校验回执。基线三点使用原功耗批次保留的负载输入和 golden。'
                  '历史修复及旧参考模型的执行入口已退役。', '']
    output.with_suffix('.md').write_text('\n'.join(lines))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, default=ROOT / 'hw/power/plans/latest_six_retained.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'hw/power/records/latest_six_retained')
    args = parser.parse_args()
    summary = generate(args.selection.resolve(), args.output.resolve())
    print('PASS current six architectures,', len(summary['results']), 'power points')


if __name__ == '__main__':
    main()
