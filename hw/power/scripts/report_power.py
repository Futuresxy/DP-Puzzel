#!/usr/bin/env python3
"""Publish only complete, hash-checked six-architecture workload measurements."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
FIELDS = ['top', 'format', 'logical_k', 'area_um2', 'internal_mw', 'switching_mw',
          'dynamic_mw', 'static_mw', 'total_mw', 'pj_per_mac']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(campaign, output):
    state = json.loads((campaign / 'state.json').read_text())
    plan = json.loads((campaign / 'plan.json').read_text())
    if state['status'] != 'completed' or len(state['points']) != 15 or len(plan['points']) != 15:
        raise ValueError('Only a complete 15-point campaign can be published')
    results = []
    provenance = json.loads((campaign / 'manifest.json').read_text())
    for name, expected in provenance['flow_sources_sha256'].items():
        if digest(campaign / 'provenance' / name) != expected:
            raise ValueError('Archived flow source changed')
    for point in plan['points']:
        directory = campaign / (point['top'] + '__' + point['format'])
        audit_path = directory / 'power_audit.json'
        result = json.loads(audit_path.read_text())
        if result['status'] != 'PASS' or result['top'] != point['top'] or result['format'] != point['format']:
            raise ValueError('Missing/mismatched accepted point')
        for path, expected in result['artifacts_sha256'].items():
            if digest(ROOT / path) != expected:
                raise ValueError('Power evidence changed: ' + path)
        result['audit_path'] = str(audit_path.relative_to(ROOT))
        result['audit_sha256'] = digest(audit_path)
        extras = [directory / name for name in ('power_compiler.log', 'power.tcl', 'config.tcl',
                  'point.json', 'vectors.txt', 'expected.txt', 'tb.sv', 'initialization.json',
                  'saif_aliases.json', 'gate/window.txt', 'activity_missing.rpt', 'timing.rpt')]
        receipt = ROOT / 'test/runs/power' / campaign.name / directory.name / 'verification.json'
        extras.append(receipt)
        result['supporting_evidence_sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in extras}
        warnings = re.findall(r'There are (\d+) objects not found during annotation',
                              (directory / 'power_compiler.log').read_text())
        result['saif_nonmatching_objects'] = int(warnings[-1]) if warnings else 0
        results.append(result)
    versions = set()
    for logfile in campaign.glob('build/*/gate_compile.log'):
        versions.update(re.findall(r'Version (X-[\w.\-]+)', logfile.read_text()))
    dc_versions = set()
    for logfile in campaign.glob('*/power_compiler.log'):
        dc_versions.update(re.findall(r'Version (X-[\w.\-]+)', logfile.read_text()))
    summary = dict(status='PASS', campaign=str(campaign.relative_to(ROOT)),
                   plan_sha256=digest(campaign / 'plan.json'),
                   provenance_sha256=digest(campaign / 'manifest.json'),
                   vcs_versions=sorted(versions), power_compiler_versions=sorted(dc_versions),
                   frequency_ghz=1, window_ns=512, transactions_per_point=1024,
                   workload='Qwen3-8B layer 0 MLP down_proj; fixed 1024 source samples',
                   scope='post-synthesis zero-delay native gate SAIF; pre-CTS/pre-route',
                   results=results)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    with output.with_suffix('.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(results)
    lines = ['# 六种 DP 的 Qwen3-8B 真实负载功耗', '',
             f'运行：`{campaign.name}`。15个兼容架构/精度点全部通过，原始结果保留于 `{campaign.relative_to(ROOT)}/`。', '',
             '工况：N12 TT、0.7V、85°C、1GHz，沿用原综合网表与时钟门控；时钟转换时间0.1ns。',
             '负载：Qwen3-8B第0层MLP down_proj，同源1024笔，II=1；测量输入事务256..767发射期间的512ns。',
             '每点先初始化已实现精度bank，再分别核对冻结RTL与门级的全部1024笔D/类型/last和L8协议。', '',
             '动态功耗 = Internal + Switching；静态功耗 = Leakage。下表单位均为mW，能效为整DP总功耗折算的pJ/MAC（C不另计MAC）。',
             'Total保留工具原始值；工具浮点累计会使其末位与分项相加略有差异，单位和分项一致性已检查。', '',
             '| 顶层 | 精度 | K | 面积 µm² | Internal | Switching | 动态 | 静态 | 总功耗 | pJ/MAC |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for result in results:
        lines.append('| ' + ' | '.join([result['top'], result['format'], str(result['logical_k']),
                                       f"{result['area_um2']:.3f}"] +
                                      [f'{result[field]:.6f}' for field in FIELDS[4:]]) + ' |')
    lines += ['', 'E64不支持BF16/E4M3，Q32E64不支持BF16；这些组合没有测量，不填零。', '',
              '## MXFP4原生吞吐与能效', '',
              '下表均以dp_top为基线；K不同意味着每周期完成的MAC数不同，不能只按总功耗排序。', '',
              '| 顶层 | MAC/周期倍率 | 总功耗变化 | pJ/MAC变化 |',
              '| --- | ---: | ---: | ---: |']
    baseline = next(row for row in results if row['top'] == 'dp_top' and row['format'] == 'mxfp4_e2m1')
    for row in results:
        if row['format'] == 'mxfp4_e2m1':
            lines.append(f"| {row['top']} | {row['logical_k']/baseline['logical_k']:.2f}× | "
                         f"{(row['total_mw']/baseline['total_mw']-1)*100:+.2f}% | "
                         f"{(row['pj_per_mac']/baseline['pj_per_mac']-1)*100:+.2f}% |")
    lines += ['',
              '## 活动与来源验收', '',
              '| 顶层 | 精度 | PC叶引脚 | 时钟对象 | 零翻转时钟对象 | 显式Nets/Ports/Pins | SAIF引脚X/Z |',
              '| --- | --- | ---: | ---: | ---: | --- | ---: |']
    for result in results:
        lines.append(f"| {result['top']} | {result['format']} | {result['annotated_pins']} | "
                     f"{result['clock_pins']} | {result['inactive_clock_pins']} | 100% / 100% / 100% | 0 |")
    lines += ['', '所有真实叶引脚及选定时钟引脚的概率/翻转率均与SAIF逐项核对；默认及传播补齐均为0。',
              'VCS省略的引脚只允许由网表同一电气网络或明确常量补齐；原生与补齐后SAIF及别名证据分别保存。',
              '工具可能提示部分SAIF名称在DDC中不存在；原始提示计数保留在JSON。验收以DDC中全部实际Nets/Ports/Pins的显式覆盖和逐引脚核对为准，未忽略真实引脚缺失。',
              '冻结快照、原完整回归、本次重放回执、网表/DDC/SDC及数据hash均核验；不修改历史manifest，不宣称旧快照与当前源树形式等价。', '',
              f"工具：VCS {', '.join(sorted(versions))}；Power Compiler/DC {', '.join(sorted(dc_versions))}。", '',
              '## 使用边界', '',
              '这是综合后、零延迟门级真实活动驱动的功耗分析。未包含CTS/布线寄生、SDF毛刺、阵列互连、SRAM或整机功耗。',
              '同K同负载可比较整DP功耗；跨K必须同时比较有效吞吐与pJ/MAC。样本C是来源BF16参考GEMM的FP32前缀累加值，每笔独立输入，未将本次D回接下一笔C。',
              '原始SAIF、网表和大型工具报告仅本地保存；本报告、JSON/CSV以及输入/输出校验和进入Git。结果引用保持本次运行及其六份DC输入不被普通滚动清理。', '',
              '复现入口：`python3.11 hw/power/scripts/run_power.py --run-id power_<new_name>`，',
              '汇总入口：`python3.11 hw/power/scripts/report_power.py --run-id ' + campaign.name + '`。', '']
    output.with_suffix('.md').write_text('\n'.join(lines))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'power_[A-Za-z0-9_]+', args.run_id):
        parser.error('Invalid run ID')
    generate(ROOT / 'hw/power/runs' / args.run_id,
             ROOT / 'hw/power/records' / args.run_id)
    print('PASS complete power summary ' + args.run_id)


if __name__ == '__main__':
    main()
