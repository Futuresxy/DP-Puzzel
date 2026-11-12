#!/usr/bin/env python3
"""Consolidate the explicitly selected 11 accepted DP designs; never run EDA."""
import csv
from datetime import datetime
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
SOURCES = (
    'hw/dc_syn/records/v19_six_dp_20261110.json',
    'hw/power/records/v19_six_architectures_20261110.json',
    'hw/dc_syn/records/five_expansions_20261112.json',
    'hw/power/records/five_expansions_20261112.json',
    'hw/power/plans/latest_six_retained.json',
    'hw/power/records/latest_six_retained.json',
    'hw/dc_syn/maintenance/final_six_dependency_retirement.json',
)
MODES = ('bf16', 'mxfp8_e4m3', 'mxfp4_e2m1')
LABELS = dict(zip(MODES, ('BF16', 'MXFP8 E4M3', 'MXFP4 E2M1')))


def local(name):
    path = ROOT / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(ROOT):
        raise ValueError(f'Non-repository path: {name}')
    return path


def read(name):
    return json.loads(local(name).read_text())


@lru_cache(maxsize=None)
def digest(name):
    with local(name).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_hash(name, expected):
    require(digest(name) == expected, f'Hash mismatch: {name}')


def main():
    old_dc, old_power, new_dc, new_power, selection, retained, retirement = map(read, SOURCES)
    require(all(x['status'] == 'PASS' for x in (old_power, new_dc, new_power, retained)), 'Source report not PASS')
    require(len(old_dc['records']) == 6 and len(new_dc['records']) == 5, 'Expected six old and five new designs')
    require(len(old_power['results']) == len(new_power['results']) == 15, 'Expected 15 old and 15 new points')
    require(retained['retirement_receipt'] == SOURCES[6], 'Unexpected retirement policy')
    check_hash(SOURCES[6], retained['retirement_receipt_sha256'])
    retained_points = {(p['top'], p['format']): p for p in retained['results']}
    selected = {(p['top'], p['format']): p for p in selection['points']}
    compare_fields = ('logical_k', 'area_um2', 'dynamic_mw', 'static_mw', 'total_mw', 'pj_per_mac', 'dc_run', 'export_id', 'campaign', 'audit_sha256')
    for point in old_power['results']:
        key = point['top'], point['format']
        require(all(point[k] == retained_points[key][k] for k in compare_fields), f'Retained old result differs: {key}')
        require(selected[key]['campaign'] == point['campaign'], f'Retained selection differs: {key}')
    designs = old_dc['records'] + new_dc['records']
    require(len({d['top'] for d in designs}) == 11, 'Duplicate designs')
    rows, expected_keys = [], set()
    design_metadata = {}
    for index, design in enumerate(designs):
        old = index < 6
        source_dc, source_power = SOURCES[:2] if old else SOURCES[2:4]
        points = [p for p in (old_power if old else new_power)['results'] if p['top'] == design['top']]
        has_full_frontend = design['capacity'].startswith('T8H16')
        capacities = (8 if has_full_frontend else 0, 16 if has_full_frontend else 0, design['q_native'], design['e_native'])
        capacity = 'T{}H{}Q{}E{}'.format(*capacities)
        native = dict(zip(MODES, capacities[1:]))
        expected_keys.update((design['top'], mode) for mode in MODES if native[mode])
        result = design['result']
        require(result['flow_pass'] and result['setup'] == result['hold'] == 'PASS', 'DC not accepted')
        require(design['multi_vt']['status'] == 'PASS' and not design['electrical_violations'], 'DC electrical/VT not accepted')
        resolved_path = design['run'] + '/inputs/resolved.json'
        resolved = read(resolved_path)
        constraints = resolved['constraints']
        summary_path = design['run'] + '/summary.json'
        summary = read(summary_path)
        require(summary['flow_pass'], 'Final DC summary not accepted')
        require(summary['area']['total_cell_area_um2'] == result['total_area_um2'], 'DC summary area differs')
        strategy = constraints['constraint_id']
        buffers = len((design.get('design_rule_repair') or {}).get('insert_hold_buffers', []))
        if design['top'] == 'dp_top_t8h16q128e256':
            require(buffers == 8, 'Expected eight accepted hold repair buffers')
        metadata = dict(capacity=capacity, design=design, old=old, strategy=strategy, buffers=buffers, constraints=constraints)
        design_metadata[design['top']] = metadata
        for point in points:
            require(point['status'] == 'PASS' and point['saif_audit']['status'] == 'PASS', 'Power not accepted')
            require(point['logical_k'] == native[point['format']], 'Non-native workload K')
            require(point['saif_audit']['missing_power_pins'] == point['saif_audit']['power_pin_xz'] == 0, 'Missing/unknown power activity')
            require(point['duration_ns'] == 512, 'Unexpected SAIF window')
            require(point['area_um2'] == result['total_area_um2'], 'Power/DC area mismatch')
            require(point['export_id'] == design['export_id'] and point['dc_run'] == design['run'], 'Power/DC source mismatch')
            require(point['frequency_hz'] == design['frequency_mhz'] * 1e6 == 1e9, 'Frequency mismatch')
            require(point['technology']['technology_id'] == design['technology']['technology_id'], 'PVT mismatch')
            require(math.isclose(point['dynamic_mw'] + point['static_mw'], point['total_mw'], rel_tol=2e-5, abs_tol=1e-6), 'Power component mismatch')
            require(math.isclose(point['pj_per_mac'], point['total_mw'] * 1e9 / point['frequency_hz'] / point['logical_k'], rel_tol=1e-12), 'MAC energy mismatch')
            check_hash(point['audit_path'], point['audit_sha256'])
            check_hash(point['workload_receipt'], point['workload_receipt_sha256'])
            receipt = read(point['workload_receipt'])
            require(receipt['status'] == 'passed' and receipt['latency'] == 8 and receipt['ii'] == 1, 'Workload receipt mismatch')
            require(receipt['workload_transactions'] == 1024, 'Unexpected workload size')
            for name, sha in point['artifacts_sha256'].items():
                check_hash(name, sha)
            point_path = str(Path(point['audit_path']).parent / 'point.json')
            point_input = read(point_path)
            for artifact in point_input['artifacts'].values():
                check_hash(artifact['path'], artifact['sha256'])
            dataset = point_input['dataset_directory']
            retained_dataset = retirement['retained_datasets'].get(dataset, dataset)
            require(local(retained_dataset).is_dir(), 'Missing retained workload evidence')
            for name, sha in point_input['dataset_files_sha256'].items():
                check_hash(str(Path(retained_dataset) / name), sha)
            pvt = point['technology']['pvt']
            row = dict(
                capacity=capacity, top=point['top'], source_batch='v19_20261110_retained' if old else 'expansions_20261112',
                t_native=capacities[0], h_native=capacities[1], q_native=capacities[2], e_native=capacities[3],
                int8_native=32 if has_full_frontend else 0,
                format=point['format'], native_k=point['logical_k'], area_um2=point['area_um2'],
                internal_mw=point['internal_mw'], switching_mw=point['switching_mw'], dynamic_mw=point['dynamic_mw'],
                static_mw=point['static_mw'], total_mw=point['total_mw'], pj_per_mac=point['pj_per_mac'],
                frequency_hz=point['frequency_hz'], process=point['technology']['process'],
                dc_version=design['dc_version'], reference_dc_version=point['technology']['reference_dc_version'], wire_load_model=point['technology']['wire_load_model'],
                technology_id=point['technology']['technology_id'], corner=pvt['corner'], voltage_v=pvt['voltage_v'], temperature_c=pvt['temperature_c'],
                latency_cycles=receipt['latency'], initiation_interval_cycles=receipt['ii'], clock_gating=design['clock_gating'],
                saif_window_ns=point['duration_ns'], workload_transactions=receipt['workload_transactions'],
                setup_slack_ps=result['setup_slack_ns'] * 1000, hold_slack_ps=result['hold_slack_ns'] * 1000,
                dc_constraint_id=strategy, hierarchy_expand_modules=';'.join(constraints['hierarchy']['expand_modules']), hold_repair_buffer_count=buffers,
                dc_created_at=design['time'], dc_finished_utc=summary['finished_utc'], power_finished_utc=point['finished_utc'],
                power_finished_asia_shanghai=datetime.fromisoformat(point['finished_utc']).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(),
                dc_run_id=Path(design['run']).name, power_run_id=Path(point['campaign']).name, export_id=point['export_id'],
                dc_verification_id=design['verification_id'], dc_verification_receipt_sha256=design['verification_receipt_sha256'],
                power_original_verification_id=point['original_verification_id'], workload_receipt=point['workload_receipt'], workload_receipt_sha256=point['workload_receipt_sha256'],
                power_audit=point['audit_path'], power_audit_sha256=point['audit_sha256'],
                retained_workload_directory=retained_dataset, retained_workload_check='PASS', retained_power_artifacts_check='PASS',
                dc_summary=summary_path, dc_summary_sha256=digest(summary_path), dc_resolved=resolved_path, dc_resolved_sha256=digest(resolved_path),
                dc_source_record=source_dc, dc_source_record_sha256=digest(source_dc),
                power_source_record=source_power, power_source_record_sha256=digest(source_power),
                status='PASS', scope='post_synthesis_pre_CTS_zero_delay_gate_SAIF')
            rows.append(row)
    require(len(rows) == 30 and {(r['top'], r['format']) for r in rows} == expected_keys, 'Incomplete/duplicate point selection')
    output = ROOT / 'hw/data/dp_latest_area_power_20261112'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_suffix('.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        '# 当前 11 种 DP 的面积与真实负载功耗（2026-11-12）', '',
        '汇总 11 种已验收架构、30 个兼容精度测量点：旧六种 15 点沿用 2026-11-09～10 的测量，新增五种 15 点为 2026-11-12 测量。旧六种本次仅复核保留证据，没有重新综合或采样。逐点精确数值、实际完成时间、run/export/verification ID、来源路径及 SHA-256 见 [CSV](dp_latest_area_power_20261112.csv)。', '',
        '统一工况：N12 BWP6T16P96CPD 120a，TT / 0.7 V / 85 °C，1 GHz，ICG 开启，L8 / II=1。每点 1024 笔 Qwen3-8B MLP 真实输入，RTL 与门级重放通过；VCS 原生 SAIF 有效窗口 512 ns，显式 nets/ports/pins 注释 100%，功耗引脚无 X/Z。面积为综合标准单元面积，功耗为综合后零延迟门级活动驱动结果；尚未 CTS/布局布线，不包含真实布线寄生或时钟树实现成本。', '',
        'T/H/Q/E 表示对应精度的原生 MAC/cycle 容量，分别对应 TF32、FP16/BF16、MXFP8/MXFP6、MXFP4/NVFP4/HiF4；各模式共享资源，不能将不同模式容量相加。完整多精度架构保留 T8/H16/INT8 K32；独立 E64 与 Q32E64 没有 T/H/INT8 通路。下表只展示本轮有真实负载实测的三个代表格式；“不支持”表示硬件没有该通路。支持但未测的 FP16、TF32、INT8、MXFP8 E5M2、MXFP6、NVFP4、HiF4 不填零，也不由其他格式推算功耗。', '',
        'pJ/MAC = 总功耗(mW) × 10⁹ / 频率(Hz) / 原生 K；MAC 按一次乘加计，OP 若需换算为 2 OP/MAC。不同原生 K 的每周期工作量不同，因此 pJ/MAC 用于单位工作量比较；本表不声称端到端 GEMM 延迟。', '',
        '| 完整容量 | 面积 (µm²) | BF16 K / 总功耗 mW | MXFP8 E4M3 K / 总功耗 mW | MXFP4 E2M1 K / 总功耗 mW | 来源批次 |',
        '|---|---:|---:|---:|---:|---|',
    ]
    for top, info in design_metadata.items():
        selected_rows = {r['format']: r for r in rows if r['top'] == top}
        values = [f"{selected_rows[m]['native_k']} / {selected_rows[m]['total_mw']:.6f}" if m in selected_rows else '不支持' for m in MODES]
        lines.append(f"| {info['capacity']}{' (opt)' if top.endswith('_opt') else ''} | {info['design']['result']['total_area_um2']:.6f} | " + ' | '.join(values) + f" | {'旧六种' if info['old'] else '新增五种'} |")
    lines += ['', '各点动态、静态和总功耗如下。动态 = Internal + Switching；保留工具原始 Total，故最后若干小数位可能与分项相加存在报告精度差异。', '',
              '| 完整容量 | 格式 | 原生 K | 动态 mW | 静态 mW | 总功耗 mW | pJ/MAC | 完成时间 (Asia/Shanghai) |', '|---|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        lines.append(f"| {r['capacity']} | {LABELS[r['format']]} | {r['native_k']} | {r['dynamic_mw']:.6f} | {r['static_mw']:.6f} | {r['total_mw']:.6f} | {r['pj_per_mac']:.9f} | {r['power_finished_asia_shanghai'][:19]} +08:00 |")
    lines += ['', '综合约束和实现差异需要随数值一起比较。下列 11 份最终网表均通过 1 GHz setup/hold、电气和 ≤20% LVT 门禁；setup 裕量非常小，仅表明当前综合模型通过，不能外推为后端时序签核。', '',
              '策略 A：仅展开 DFF 包装层，保留算术模块层级。策略 B：在 A 上进一步展开 MAX、全局/局部对齐、移位、LZD、scale、指数加法和最终舍入组合层；保留 lane/group/top 和 S7 CSA。所有时钟、IO、PVT、门控、VT 预算保持一致。E256 与 Q128E256 使用 B，其面积/功耗变化包含映射策略影响，不能全部归因于容量变化。', '',
              'T8H16Q128E256 的最终网表在输入→S1 分支加入 8 个同极性延迟 buffer 修复 hold；相对同策略修复前网表增加 2.949120 µm²，已计入下表面积。没有增加流水，S1～S8 setup 均为正。', '',
              '| 完整容量 | 策略 | Setup slack ps | Hold slack ps | DC run | Power run |', '|---|---|---:|---:|---|---|']
    for top, info in design_metadata.items():
        r = next(r for r in rows if r['top'] == top)
        lines.append(f"| {r['capacity']} | {'B' if 'align-flat' in r['dc_constraint_id'] else 'A'} | {r['setup_slack_ps']:.6f} | {r['hold_slack_ps']:.6f} | `{r['dc_run_id']}` | `{r['power_run_id']}` |")
    lines += ['', '来源核验：旧 15 点与 `latest_six_retained.json` 的选择、面积和功耗逐值一致；30 点的功耗审计、RTL 工作负载回执、功耗原始产物、最终网表/DDC/SDC 及保留输入/golden 均核对 SHA-256。旧 baseline 原 CModel 目录和两份被替代修复源已按清理回执删除；复核采用批次内 `workload_evidence` 与清理前修复链回执，不声称旧执行环境全部保留。源 DC 记录中的历史 `power_preparation` 是当时准备状态，当前功耗通过状态以对应最终 power report 为准。', '',
              '| 来源记录 | SHA-256 |', '|---|---|']
    for path in SOURCES:
        lines.append(f'| [{path}](../../{path}) | `{digest(path)}` |')
    lines += ['', '复现汇总（只读取并校验上述显式记录，不启动 EDA）：', '',
              '```bash', 'python3.11 hw/power/scripts/report_latest_dp_data.py', '```', '',
              'CSV 保留 JSON 原始浮点精度；Markdown 仅为显示舍入。所有路径均相对于仓库根。']
    output.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(f'PASS: 11 designs / 30 native precision points; {output.relative_to(ROOT)}.{{csv,md}}')


if __name__ == '__main__':
    main()
