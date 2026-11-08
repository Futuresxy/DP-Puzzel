#!/usr/bin/env python3
"""Publish the latest passing result for each of the six supported DP architectures.

This audits archived measurement inputs. It never refreshes an RTL gate receipt,
launches EDA, or qualifies a netlist for workload power without GLS/SAIF evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from run_dc import ROOT, DC, verify_repair_source
from report_dc import analyze, compact_record
from compare_mixed import clock_gating
from rtl_gate import rtl_fingerprint

PROFILES = (
    ('dp_top', 'T8H16Q32E64', 'multi', 32, 64),
    ('dp_top_t8h16q32e96', 'T8H16Q32E96', 't8h16q32e96', 32, 96),
    ('dp_top_t8h16q32e128', 'T8H16Q32E128', 't8h16q32e128', 32, 128),
    ('dp_top_t8h16q64e128_opt', 'T8H16Q64E128 opt', 't8h16q64e128_opt', 64, 128),
    ('dp_top_e64', 'E64', 'e64', 0, 64),
    ('dp_top_q32e64', 'Q32E64', 'q32e64', 32, 64),
)
MOVED = {'src/verilog/top/'+name+'.v': 'src/verilog/top/common/'+name+'.v'
         for name in ('dp_global_align','dp_mixed_global_align','dp_top_mixed','dp_top_lowp')}
FLOAT_MODES = ['tf32','fp16','bf16','mxfp8_e4m3','mxfp8_e5m2',
               'mxfp6_e3m2','mxfp6_e2m3','mxfp4_e2m1','nvfp4','hif4']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_runs():
    selected={}
    tops={item[0] for item in PROFILES}
    for run in (DC/'runs').iterdir():
        if not run.is_dir():continue
        if run.is_symlink() or (run/'.running').exists():
            raise ValueError('Active or symlinked run: '+run.name)
        state=json.loads((run/'state.json').read_text())
        if state['phase'] not in ('finished','failed'):
            raise ValueError('Unfinished run: '+run.name)
        data=json.loads((run/'inputs/resolved.json').read_text())
        top=data['gate']['top']
        if top not in tops:continue
        measured=analyze(run,data)
        if not measured['flow_pass']:continue
        if top not in selected or state['finished_utc']>selected[top][0]:
            selected[top]=(state['finished_utc'],run,data,measured)
    if set(selected)!=tops:raise ValueError('Missing passing architecture: '+str(tops-set(selected)))
    return selected


def record(run, data, measured, profile):
    top,capacity,frontend,q_count,e_count=profile
    verify_repair_source(data)
    export=ROOT/'hw/rtl'/measured['export_id']
    manifest=json.loads((export/'manifest.json').read_text())
    if rtl_fingerprint(export)!=measured['rtl_fingerprint']:
        raise ValueError('Archived RTL fingerprint changed: '+run.name)
    for name,expected in manifest['exported_sha256'].items():
        if digest(export/name)!=expected:raise ValueError('Snapshot payload changed: '+name)
    receipt=ROOT/'test/runs/verilog'/data['gate']['verification_id']/'verification.json'
    evidence=json.loads(receipt.read_text())
    if not (evidence['export_id']==export.name and evidence['rtl_fingerprint']==measured['rtl_fingerprint']
            and evidence['status']=='passed' and evidence['numerical_pass'] and evidence['protocol_pass']):
        raise ValueError('Original verification receipt mismatch')
    for scope in evidence['scopes']:
        for path_key,hash_key in [('input_path','input_sha256'),('results_path','output_sha256')]:
            if digest(ROOT/scope[path_key])!=scope[hash_key]:raise ValueError('Original simulation data changed')
    if set(measured['stage_setup_paths'])!={f'S{i}' for i in range(1,9)}:
        raise ValueError('Missing complete L8 timing reports')
    if '\tunclassified' in (run/'reports/register_stages.tsv').read_text():
        raise ValueError('Unclassified pipeline registers')
    result=compact_record(measured)
    result.update(top=top,capacity=capacity,frontend=frontend,q_native=q_count,e_native=e_count,
                  verification_id=evidence['verification_id'],
                  verification_receipt_sha256=digest(receipt),
                  evidence_scope='archived_snapshot_and_original_receipt',
                  clock_gating_measurement=clock_gating(run))
    artifacts={}
    for role,suffix in [('mapped_verilog','_mapped.v'),('ddc','.ddc'),('sdc','.sdc')]:
        path=run/'netlist'/(top+suffix)
        artifacts[role]={'path':str(path.relative_to(ROOT)),'sha256':digest(path),'bytes':path.stat().st_size}
    changed=[]
    moved=[]
    for old,expected in manifest['source_sha256'].items():
        current=MOVED.get(old,old)
        if current!=old:moved.append({'snapshot_path':old,'current_path':current})
        if not (ROOT/current).is_file() or digest(ROOT/current)!=expected:changed.append(current)
    modes=FLOAT_MODES[7:] if frontend=='e64' else FLOAT_MODES[3:] if frontend=='q32e64' else FLOAT_MODES+['int8']
    result['power_preparation']={
        'status':'synthesis_artifacts_retained_not_power_validated',
        'power_ready':False,'power_mw':None,'artifacts':artifacts,'supported_modes':modes,
        'current_source_content_differences':changed,'source_relocations':moved,
        'current_source_gate_revalidation_required':True,
        'pending':['select matched workload and active measurement window',
                   'validate the exact RTL input scope used for power',
                   'VCS mapped-netlist numerical/protocol equivalence using exact cell models',
                   'VCS native gate-level SAIF capture',
                   'Power Compiler annotation and leaf-pin activity audit']}
    return result


def collect():
    selected=latest_runs();records=[];common=None
    for profile in PROFILES:
        _,run,data,measured=selected[profile[0]]
        condition={key:data[key] for key in ('technology','constraints','target_dbs')}
        condition.update(parameters=data['gate']['parameters'],dc_version=measured['dc_version'])
        if common is not None and common!=condition:raise ValueError('Mismatched synthesis conditions')
        common=condition;records.append(record(run,data,measured,profile))
    baseline=records[0]['result']['total_area_um2']
    for entry in records:entry['area_delta_percent']=100*(entry['result']['total_area_um2']/baseline-1)
    return {'schema_version':1,'audited_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'six latest passing archived measurements; not new synthesis or power',
            'records':records}


def markdown(catalog):
    lines=['# 六种 DP 最新综合结果与功耗输入索引','',
      '此表是已完成实验的最新有效结果汇总。本次只核验、整理及清理，没有重新综合或测量功耗。所有结果保持 **L8/II=1、K16/LOCAL28/GLOBAL40、1GHz、ICG开启**。',
      '', '| 架构 | 面积 µm² | 相对dp_top | setup ps | hold ps | 验收 |',
      '| --- | ---: | ---: | ---: | ---: | --- |']
    for rec in catalog['records']:
        r=rec['result'];lines.append(f"| {rec['capacity']} | {r['total_area_um2']:.2f} | {rec['area_delta_percent']:+.2f}% | {r['setup_slack_ns']*1000:.6f} | {r['hold_slack_ns']*1000:.6f} | PASS |")
    lines+=['','验收包括映射完整、setup/hold、VT及电气规则。工况：TSMC CLN12FFCLL BWP6T16P96CPD、120a、TT/0.7V/85°C，base+LVT≤20%；DC X-2025.06，ZeroWireload。周期1ns，setup/hold uncertainty=0.1/0.03ns，IO max/min=0.2/0ns，输出负载0.01pF。所有run的工具/参数/库/最终约束已逐项核对一致。极小正slack只代表指定TT角的预布局综合通过。',
      '', '## 六份保留结果', '', '| 顶层 | 最终run及报告 | ICG | 门控寄存器 |', '| --- | --- | ---: | ---: |']
    for rec in catalog['records']:
        run=Path(rec['run']).name;g=rec['clock_gating_measurement']
        lines.append(f"| `{rec['top']}` | [{run}](../runs/{run}/REPORT.md) | {g['gating_elements']} | {g['gated_registers']}/{g['total_registers']} ({g['gated_percent']:.2f}%) |")
    lines+=['','每个最终run保留原始reports、日志、映射网表、DDC、SDC及配置。修复来源收在对应run的provenance/repair_sources/中，目录内容和hash清单保留；它们是最终结果的必要依赖，不作为额外候选结果。',
      '', '## 后续功耗测试准备', '',
      '机器可读入口为 [latest_six_dp.json](latest_six_dp.json)。每个条目固定top、run、export、原始验证回执、PVT/频率、支持模式，以及映射网表/DDC/SDC路径与SHA-256。未来功耗应显式选择该记录中的一份网表，按精度测量，不能用模糊latest目录或混用另一个run的活动信息。',
      '', '当前power_ready=false，power_mw=null：尚未执行VCS门级等价重放、原生SAIF捕获或Power Compiler活动注释审计。流程见 [功耗准备说明](../../power/README.md)。时钟门控覆盖率不是功耗数据。',
      '', '现用源码经历顶层common目录搬移，部分旧混合快照还早于QE紧凑解包的共用源码更新。JSON逐文件列出当前源码与冻结源码的差异；差异不直接证明数值改变，也不能被忽略当作同一源码。旧快照仍绑定其原始通过回执；新EDA输入必须按选定范围重新验证，不能手改旧manifest。',
      '', '## 捕获级 setup slack（ps）', '', '| 架构 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for rec in catalog['records']:
        lines.append('| '+rec['capacity']+' | '+' | '.join(f"{rec['stage_setup_paths'][f'S{i}']['slack_ns']*1000:.6f}" for i in range(1,9))+' |')
    lines+=['','各列为捕获到该级端点的最差路径，不保证起点一定在相邻前级；具体起止点保存在JSON和原始报告中。',
      '', '复核/重建当前汇总（只读取证据，不启动EDA）：', '', '```bash',
      'python3.11 hw/dc_syn/scripts/latest_synthesis.py --write', '```','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Publish audited records; never delete runs')
    args=parser.parse_args();catalog=collect()
    if args.write:
        (DC/'records/latest_six_dp.json').write_text(json.dumps(catalog,indent=2,ensure_ascii=False)+'\n')
        (DC/'records/latest_six_dp.md').write_text(markdown(catalog))
    print(json.dumps([{'top':r['top'],'run':r['run'],'area_um2':r['result']['total_area_um2'],
                      'source_differences':r['power_preparation']['current_source_content_differences']}
                     for r in catalog['records']],indent=2))

if __name__=='__main__':main()
