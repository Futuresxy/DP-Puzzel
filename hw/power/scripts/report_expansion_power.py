#!/usr/bin/env python3
"""Audit explicit completed expansion campaigns before publishing their results."""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from dp_power_gate import verify_workload_replay
from report_power import FIELDS, digest

CAPACITIES = {'dp_top_t8h16q64e64': (64, 64),
              'dp_top_t8h16q32e192': (32, 192),
              'dp_top_t8h16q32e256': (32, 256),
              'dp_top_t8h16q96e192': (96, 192), 'dp_top_t8h16q128e256': (128, 256)}
MODES = ('bf16', 'mxfp8_e4m3', 'mxfp4_e2m1')


def read(path):
    return json.loads(path.read_text())


def local(name):
    path = (ROOT / name).resolve()
    path.relative_to(ROOT)
    return path


def check_scope(points):
    identities = [(point['top'], point['format']) for point in points]
    tops = {top for top, _ in identities}
    if not tops or not tops <= CAPACITIES.keys():
        raise ValueError('Unknown or empty expansion profile selection')
    expected = {(top, mode) for top in tops for mode in MODES}
    if len(identities) != len(expected) or set(identities) != expected:
        raise ValueError('Each selected profile requires exactly three distinct precision points')
    for point in points:
        q_k, e_k = CAPACITIES[point['top']]
        native = dict(bf16=16, mxfp8_e4m3=q_k, mxfp4_e2m1=e_k)
        if point['logical_k'] != native[point['format']]:
            raise ValueError('Workload K does not match the native precision capacity')


def generate(campaigns, output):
    batches = []
    all_points = []
    for name in campaigns:
        campaign = local(name)
        plan = read(campaign / 'plan.json')
        state = read(campaign / 'state.json')
        manifest = read(campaign / 'manifest.json')
        if state['status'] != 'completed':
            raise ValueError('Campaign did not complete: ' + str(name))
        expected = {point['top'] + '__' + point['format'] for point in plan['points']}
        if (len(state['points']) != len(expected)
                or {point['point'] for point in state['points']} != expected
                or any(point['status'] != 'PASS' for point in state['points'])):
            raise ValueError('Incomplete campaign point status')
        if digest(campaign / 'plan.json') != manifest['plan_sha256']:
            raise ValueError('Campaign plan changed')
        for path, expected_hash in manifest['flow_sources_sha256'].items():
            if digest(campaign / 'provenance' / path) != expected_hash:
                raise ValueError('Archived flow changed: ' + path)
        batches.append((campaign, plan))
        all_points.extend(plan['points'])
    check_scope(all_points)
    common = None
    results = []
    vcs_versions = set()
    compiler_versions = set()
    for campaign, plan in batches:
        for logfile in campaign.glob('build/*/gate_compile.log'):
            vcs_versions.update(re.findall(r'Version (X-[\w.\-]+)', logfile.read_text()))
        for point in plan['points']:
            directory = campaign / (point['top'] + '__' + point['format'])
            audit_path = directory / 'power_audit.json'
            result = read(audit_path)
            if read(directory / 'point.json') != point or result['status'] != 'PASS':
                raise ValueError('Point plan mismatch or unaccepted result')
            for key in ('top', 'format', 'logical_k', 'dc_run', 'export_id'):
                if result[key] != point[key]:
                    raise ValueError('Point identity mismatch: ' + key)
            for path, expected_hash in result['artifacts_sha256'].items():
                if digest(local(path)) != expected_hash:
                    raise ValueError('Power evidence changed: ' + path)
            dataset = local(point['dataset_directory'])
            if digest(dataset / 'manifest.json') != point['dataset_manifest_sha256']:
                raise ValueError('Dataset manifest changed')
            for path, expected_hash in point['dataset_files_sha256'].items():
                if digest(dataset / path) != expected_hash:
                    raise ValueError('Dataset changed: ' + path)
            receipt = ROOT / 'test/runs/power' / campaign.name / directory.name / 'verification.json'
            gate = verify_workload_replay(ROOT, point, receipt)
            resolved = gate['resolved']
            pvt = result['technology']['pvt']
            if (pvt != dict(corner='TT', voltage_v=0.7, temperature_c=85)
                    or resolved['constraints']['period_ns'] != 1
                    or not resolved['constraints']['clock_gating']
                    or result['frequency_hz'] != 1e9 or result['duration_ns'] != 512):
                raise ValueError('Unexpected measurement condition')
            summary = read(local(point['dc_run']) / 'summary.json')
            if result['area_um2'] != summary['area']['total_cell_area_um2']:
                raise ValueError('Area differs from the selected DC result')
            condition = dict(technology=result['technology'], frequency_hz=result['frequency_hz'],
                             duration_ns=result['duration_ns'], clock_slew_ns=result['clock_slew_ns'],
                             window=plan['measurement_window'])
            if common is not None and condition != common:
                raise ValueError('Mixed measurement conditions')
            common = condition
            if (not math.isclose(result['dynamic_mw'], result['internal_mw'] + result['switching_mw'])
                    or not math.isclose(result['pj_per_mac'], result['total_mw'] / point['logical_k'])):
                raise ValueError('Inconsistent derived power or energy units')
            result.update(campaign=str(campaign.relative_to(ROOT)),
                          audit_path=str(audit_path.relative_to(ROOT)), audit_sha256=digest(audit_path),
                          workload_receipt=str(receipt.relative_to(ROOT)),
                          workload_receipt_sha256=digest(receipt),
                          original_verification_id=point['original_verification_id'])
            evidence = [directory / name for name in
                        ('power_compiler.log', 'power.tcl', 'config.tcl', 'point.json',
                         'vectors.txt', 'expected.txt', 'tb.sv', 'initialization.json',
                         'saif_aliases.json', 'gate/window.txt', 'activity_missing.rpt', 'timing.rpt')]
            result['supporting_evidence_sha256'] = {str(path.relative_to(ROOT)): digest(path)
                                                   for path in evidence}
            compiler_versions.update(re.findall(r'Version (X-[\w.\-]+)',
                                                 (directory / 'power_compiler.log').read_text()))
            results.append(result)
    if not vcs_versions or not compiler_versions:
        raise ValueError('Missing measured EDA tool versions')
    result = dict(schema_version=1, status='PASS', audited_utc=datetime.now(timezone.utc).isoformat(),
                  scope='post-synthesis zero-delay VCS native gate SAIF; pre-CTS/pre-route',
                  condition=common, vcs_versions=sorted(vcs_versions),
                  power_compiler_versions=sorted(compiler_versions),
                  campaigns=[dict(directory=str(campaign.relative_to(ROOT)),
                                  plan_sha256=digest(campaign / 'plan.json'),
                                  manifest_sha256=digest(campaign / 'manifest.json'))
                             for campaign, _ in batches], results=results)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    with output.with_suffix('.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(results)
    lines = ['# 扩展 DP 真实负载功耗', '',
             '工况：N12 TT / 0.7 V / 85°C、1 GHz、ICG 开启、L8 / II=1。',
             '每点使用 1024 笔 Qwen3-8B MLP down_proj 原生 K 数据；活动窗口为第 256–767 笔发射期间的 512 ns。',
             '冻结 RTL 与门级逐笔一致，原生 SAIF 和逐引脚活动审计通过，Nets/Ports/Pins 全部显式注释。',
             '工具：VCS ' + ', '.join(sorted(vcs_versions)) + '；Power Compiler '
             + ', '.join(sorted(compiler_versions)) + '。',
             '动态 = Internal + Switching；静态 = Leakage。MAC 不另计 C 加数。综合后零延迟、CTS/布线前结果。', '',
             'Total 保留工具原始累计值，浮点累计会使其末位与分项之和略有差异；单位及分项一致性由功耗审计检查。', '',
             '| 顶层 | 格式 | K | 面积 µm² | Internal mW | Switching mW | 动态 mW | 静态 mW | 总功耗 mW | pJ/MAC |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in results:
        lines.append('| ' + ' | '.join([row['top'], row['format'], str(row['logical_k'])]
                                      + [f'{row[field]:.6f}' for field in FIELDS[3:]]) + ' |')
    lines += ['', '## 来源与重放', '']
    for campaign, plan in batches:
        relative = str(campaign.relative_to(ROOT / 'hw/power'))
        lines.append(f'- 批次：[{campaign.name}](../{relative}/)，计划与逐点审计保存在批次目录。')
    for row in results:
        lines.append(f"- `{row['top']}` / `{row['format']}`：DC `{row['dc_run']}`；RTL `{row['export_id']}`；原验证 `{row['original_verification_id']}`。")
    output.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.campaign, args.output)
