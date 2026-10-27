#!/usr/bin/env python3
"""Trace existing K124 RTL and attribute exact-reference errors to alignment stages.

Uses the fixed TB and explicit read-only files.f. An additional observation-only
SV root records hierarchy signals; it does not patch or copy the design RTL.
Counterfactual inputs remove exactly cancelling terms or set C=0. Their exact
references are recomputed, never substituted for the original regression data.
"""
import argparse
import atexit
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'hw/test/vectors'))
from exact_dot import (FORMATS, FP32, Operand, decode_binary, decode_element,
                       decode_scale, dequantize, dot_product, exact_sum, finite,
                       multiply, round_fp32, serialize)
from run_pe_tests import inspect_export

FORMATS_TO_TRACE = ('fp16','bf16','mxfp8_e4m3','mxfp8_e5m2','mxfp4_e2m1')
HIER = 'tb_k_1_2_4.dut'


def parse_row(line, meta):
    v = [int(x,16) for x in line.split()]
    k, ns, g0, g1 = (meta[x] for x in ('logical_k','a_scale_count','group0_count','group1_count'))
    offset = 2+2*k
    sa, sb = v[offset:offset+ns], v[offset+ns:offset+2*ns]
    offset += 2*ns
    a0, b0 = v[offset:offset+g0], v[offset+g0:offset+2*g0]
    offset += 2*g0
    return (Operand(v[2:2+k],sa,a0,v[offset:offset+g1]),
            Operand(v[2+k:2+2*k],sb,b0,v[offset+g1:offset+2*g1]),v[1])


def encode_row(txn, a, b, c):
    return ' '.join([f'{txn:08x}',f'{c:08x}']+[f'{x:04x}' for x in a.codes+b.codes]
                    +[f'{x:02x}' for x in a.scales+b.scales]
                    +[str(x) for x in a.group0+b.group0+a.group1+b.group1])


def subtract(a,b):
    return exact_sum((a,-b))


def rtz(value, quantum):
    shift = quantum-value.exponent
    coefficient = abs(value.coefficient)
    coefficient = coefficient >> shift if shift >= 0 else coefficient << -shift
    return finite(-coefficient if value.coefficient < 0 else coefficient,quantum)


def display(value):
    with localcontext() as context:
        context.prec = 24
        approximate = str(Decimal(value.coefficient)*Decimal(2)**value.exponent)
    return dict(**serialize(value),decimal=approximate)


def monitor():
    lines = ['`timescale 1ns/1ps','module precision_trace;',
             'integer fd; string path;',
             'integer sub_txn=0, pg_txn=0, pa_txn=0, pe_txn=0, t12_txn=0, t13_txn=0, t14_txn=0, final_txn=0;',
             'initial begin if (!$value$plusargs("TRACE_FILE=%s",path)) $fatal(1,"TRACE_FILE missing"); fd=$fopen(path,"w"); if (!fd) $fatal; end']
    def emit(stage,txn,slot,value,anchor,aux0='0',aux1='0'):
        return f'$fdisplay(fd,"{stage},%0d,{slot},%0d,%0d,%0d,%0d",{txn},{value},{anchor},{aux0},{aux1});'
    # Early SubPE anchor is two valid stages ahead of its data; PG raw anchor
    # is one stage ahead. Delay only observation metadata, never DUT signals.
    for group in range(4):
        pg=f'{HIER}.pe_instances_0.pe_groups_{group}'
        lines += [f'reg signed [10:0] pg_anchor_{group};',f'always @(posedge tb_k_1_2_4.clock) if ({pg}.s06_valid_q) pg_anchor_{group} <= $signed({pg}.s06_anchor_q);']
        for word in range(4):
            i=group*4+word
            sub=f'{pg}.sub_pes_{word}'
            lines += [f'reg [8:0] a0_{i},a1_{i};',
                      f'always @(posedge tb_k_1_2_4.clock) begin if ({sub}.s02_valid_q) a0_{i} <= {sub}.s02_anchor_q; if ({sub}.s03_valid_q) a1_{i} <= a0_{i}; end']
    lines += ['always @(posedge tb_k_1_2_4.clock) begin',f'if ({HIER}.pe_instances_0.pe_groups_0._sub_pes_0_io_out_data_valid) begin']
    for group in range(4):
        for word in range(4):
            i=group*4+word; pg=f'{HIER}.pe_instances_0.pe_groups_{group}'
            lines.append(emit('SUB','sub_txn',i,f'$signed({pg}._sub_pes_{word}_io_out_data_bits_result)',f'a1_{i}',f'{pg}.s04_shifts_q_{word}'))
    lines += ['sub_txn=sub_txn+1; end',f'if ({HIER}.pe_instances_0.pe_groups_0.io_out_pegroup_data_valid) begin']
    for group in range(4):
        pg=f'{HIER}.pe_instances_0.pe_groups_{group}'
        lines.append(emit('PG','pg_txn',group,f'$signed({pg}.io_out_pegroup_data_bits_mul_scale_mant)',f'pg_anchor_{group}',f'$signed({HIER}.pe_instances_0.reduction.s07_anchors_q_{group})'))
    lines += ['pg_txn=pg_txn+1; end',f'if ({HIER}.pe_instances_0.reduction.s08_valid_q) begin']
    for group in range(4):
        red=f'{HIER}.pe_instances_0.reduction'
        lines.append(emit('PA','pa_txn',group,f'$signed({red}.s08_aligned_q_{group})',f'$signed({red}.s08_raw_top_q)',f'{red}.s08_correction_q'))
    lines += ['pa_txn=pa_txn+1; end',f'if ({HIER}._pe_instances_0_io_out_data_valid) begin']
    lines.append(emit('PE','pe_txn',0,f'{HIER}._pe_instances_0_io_out_data_bits_magnitude',f'$signed({HIER}._pe_instances_0_io_out_data_bits_top_anchor)',f'{HIER}._pe_instances_0_io_out_data_bits_negative'))
    lines.append(emit('C','pe_txn',0,f'{HIER}._c_unpacker_io_out_data_bits_magnitude',f'$signed({HIER}._c_unpacker_io_out_data_bits_top_anchor)',f'{HIER}._c_unpacker_io_out_data_bits_negative'))
    lines += ['pe_txn=pe_txn+1; end',f'if ({HIER}.s12_valid_q) begin']
    for slot in range(2):
        lines.append(emit('T12','t12_txn',slot,f'{HIER}.s12_magnitudes_q_{slot}',f'$signed({HIER}.s12_top_anchor_q)',f'{HIER}.s12_negatives_q_{slot}',f'{HIER}.s12_shifts_q_{slot}'))
    lines += ['t12_txn=t12_txn+1; end',f'if ({HIER}.s13_valid_q) begin']
    for slot in range(2):
        lines.append(emit('T13','t13_txn',slot,f'$signed({HIER}.s13_terms_q_{slot})',f'$signed({HIER}.s13_top_anchor_q)'))
    lines += ['t13_txn=t13_txn+1; end',f'if ({HIER}.s14_valid_q) begin']
    lines.append(emit('T14','t14_txn',0,f'$signed({HIER}.s14_sum_q)',f'$signed({HIER}.s14_top_anchor_q)'))
    lines += ['t14_txn=t14_txn+1; end',f'if ({HIER}.io_out_result_valid) begin']
    lines.append(emit('FINAL','final_txn',0,f'{HIER}.io_out_result_bits_result','0'))
    lines += ['final_txn=final_txn+1; end','end','endmodule']
    return '\n'.join(lines)+'\n'


def variants(name,a,b,c,label):
    yield 'original',deepcopy(a),deepcopy(b),c
    if c:
        yield 'c_zero',deepcopy(a),deepcopy(b),0
    if label in ('c_exact_cancellation','c_near_cancellation'):
        left=deepcopy(a)
        left.codes[1:]=[0]*(len(left.codes)-1)
        if dot_product(name,left,b) != dot_product(name,a,b):
            raise ValueError('Counterfactual changed exact dot')
        yield 'cancelled_pairs_removed',left,deepcopy(b),c
    if name=='mxfp4_e2m1':
        av,bv=dequantize(name,a),dequantize(name,b)
        left=deepcopy(a);removed=[]
        for block in range(len(a.scales)):
            start=block*32
            if exact_sum(multiply(x,y) for x,y in zip(av[start:start+32],bv[start:start+32])).coefficient==0:
                left.codes[start:start+32]=[0]*len(left.codes[start:start+32]);removed.append(block)
        if removed:
            assert dot_product(name,left,b)==dot_product(name,a,b)
            yield 'zero_sum_scale_blocks_removed',left,deepcopy(b),c
        left,right=deepcopy(a),deepcopy(b)
        left.scales=[127]*len(left.scales);right.scales=[127]*len(right.scales)
        yield 'unit_scales',left,right,c


def analyze(name,cases,trace):
    fmt=FORMATS[name]
    lanes=1 if fmt.scale_kind=='none' else 2 if fmt.bits in (6,8) else 4
    bias2=2*fmt.bias if fmt.scale_kind=='none' else 30 if lanes==2 else 0
    sub_fraction=26 if lanes==1 else 25 if lanes==2 else 20
    pg_fraction=28 if lanes==1 else 27 if lanes==2 else 22
    data=defaultdict(lambda:defaultdict(dict))
    for line in trace.read_text().splitlines():
        stage,txn,slot,*values=line.split(',')
        data[int(txn)][stage][int(slot)]=list(map(int,values))
    results=[]
    for txn,(identity,a,b,c) in enumerate(cases):
        got=data[txn]
        assert set(got)=={'SUB','PG','PA','PE','C','T12','T13','T14','FINAL'},(txn,set(got))
        physical=[multiply(x,y) for x,y in zip(dequantize(name,a),dequantize(name,b))]
        pure=[multiply(decode_element(name,x),decode_element(name,y)) for x,y in zip(a.codes,b.codes)]
        word_values=[];word_errors=[];pg_values=[];pg_errors=[];groups=[]
        for word in range(16):
            value,anchor,*_=got['SUB'][word]
            actual=finite(value,anchor-bias2-sub_fraction)
            exact=exact_sum(pure[word*lanes:(word+1)*lanes])
            predicted=exact_sum(rtz(x,anchor-bias2-sub_fraction) for x in pure[word*lanes:(word+1)*lanes])
            assert actual==predicted,('SubPE intended RTZ mismatch',name,identity,word,actual,predicted)
            scale=multiply(decode_scale(fmt.scale_kind,a.scales[word*lanes//fmt.block]),decode_scale(fmt.scale_kind,b.scales[word*lanes//fmt.block])) if a.scales else finite(1)
            word_values.append(multiply(actual,scale));word_errors.append(multiply(subtract(actual,exact),scale))
        for group in range(4):
            value,anchor,masked,*_=got['PG'][group]
            quantum=anchor-bias2-pg_fraction
            actual=finite(value,quantum)
            previous=exact_sum(word_values[group*4:(group+1)*4])
            predicted=exact_sum(rtz(x,quantum) for x in word_values[group*4:(group+1)*4])
            assert actual==predicted,('PG intended RTZ mismatch',name,identity,group,actual,predicted)
            ideal=exact_sum(physical[group*4*lanes:(group+1)*4*lanes])
            error=subtract(actual,previous)
            pg_values.append(actual);pg_errors.append(error)
            groups.append(dict(group=group,raw_anchor=anchor,masked_anchor=masked,quantum=quantum,
                               exact=display(ideal),actual=display(actual),local_alignment_error=display(error)))
        magnitude,anchor,negative,*_=got['PE'][0]
        pe=finite(-magnitude if negative else magnitude,anchor-40)
        pe_quantum=got['PA'][0][1]-40
        predicted=exact_sum(rtz(x,pe_quantum) for x in pg_values)
        assert pe==predicted,('PE intended RTZ mismatch',name,identity,pe,predicted)
        pe_error=subtract(pe,exact_sum(pg_values))
        cm,ca,cn,*_=got['C'][0]
        decoded_c=finite(-cm if cn else cm,ca-23)
        assert decoded_c==decode_binary(FP32,c),('C decode',name,identity)
        total,top_anchor,*_=got['T14'][0]
        top=finite(total,top_anchor-41)
        top_quantum=got['T13'][0][1]-40
        predicted=exact_sum(rtz(x,top_quantum) for x in (pe,decoded_c))
        assert top==predicted,('Top intended RTZ mismatch',name,identity,top,predicted)
        actual=got['FINAL'][0][0]
        assert round_fp32(top)==actual,('Final RNE mismatch',name,identity)
        exact_dot=exact_sum(physical);exact_result=exact_sum((exact_dot,decoded_c))
        top_error=subtract(top,exact_sum((pe,decoded_c)))
        errors=[exact_sum(word_errors),exact_sum(pg_errors),pe_error,top_error]
        assert exact_sum(errors)==subtract(top,exact_result)
        first='SubPE' if any(x.coefficient for x in word_errors) else 'PEGroup' if any(x.coefficient for x in pg_errors) else 'PE' if pe_error.coefficient else 'Top' if top_error.coefficient else 'none'
        expected=round_fp32(exact_result)
        ordered=lambda x: 0x80000000-(x & 0x7fffffff) if x >> 31 else 0x80000000+x
        distance=abs(ordered(actual)-ordered(expected)) if ((actual & 0x7f800000)!=0x7f800000 and (expected & 0x7f800000)!=0x7f800000) else None
        results.append(dict(**identity,actual_hex=f'{actual:08x}',golden_hex=f'{expected:08x}',fp32_steps=distance,
                            first_loss=first,exact_dot=display(exact_dot),pe_dot=display(pe),
                            c=display(decoded_c),exact_result=display(exact_result),pre_round_result=display(top),
                            subpe_error=display(errors[0]),pegroup_error=display(errors[1]),
                            pe_error=display(pe_error),top_error=display(top_error),
                            pe_quantum=pe_quantum,top_quantum=top_quantum,groups=groups))
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run',type=Path,default=ROOT/'hw/test/runs/pe-exact-random-1600-seed24301-final')
    parser.add_argument('--output',type=Path,default=ROOT/'hw/test/runs/k124-precision-diagnosis-seed24301')
    args=parser.parse_args();source=args.source_run.resolve();out=args.output.resolve()
    source_report=json.loads((source/'report.json').read_text())
    export=source_report['exports']['k_1_2_4']
    rtl,manifest=inspect_export(export,'k_1_2_4')
    assert manifest['parameters']['layout']==['PE_HQE_g4'] and manifest['parameters']['alignment']==dict(q_align_width=28,group_guard_bits=2,pe_align_width=40,top_align_width=40)
    out.mkdir(parents=True,exist_ok=False)
    (out/'trace.sv').write_text(monitor())
    executable=out/'sim.vvp'
    atexit.register(executable.unlink,missing_ok=True)
    command=['iverilog','-g2012','-I',str(ROOT/'hw/test/tb/common'),'-s','tb_k_1_2_4','-s','precision_trace',
             '-o',str(executable),'-f','files.f',str(ROOT/'hw/test/tb/tb_k_1_2_4.sv'),str(out/'trace.sv')]
    record=dict(export_id=export,parameters=manifest['parameters'],source_run=str(source.relative_to(ROOT)),
                command=[sys.executable,*sys.argv],compile_command=command,replay_commands=[],
                tools={'python':sys.version.split()[0]})
    for tool in ('iverilog','vvp'):
        version=subprocess.run([tool,'-V'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        record['tools'][tool]=version.stdout.splitlines()[0]
    (out/'run.json').write_text(json.dumps(record,indent=2)+'\n')
    compiled=subprocess.run(command,cwd=rtl,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/'compile.log').write_text(compiled.stdout)
    if compiled.returncode:raise RuntimeError('diagnostic compile failed')
    all_results=[]
    for name in FORMATS_TO_TRACE:
        original=next(x for x in source_report['cases'] if x['profile']=='k_1_2_4' and x['format']==name)
        case=ROOT/Path(original['input']).parent
        meta=json.loads((case/'case.json').read_text())
        lines=(case/'inputs.txt').read_text().splitlines();cases=[]
        for original_txn in original['failed_transactions']:
            a,b,c=parse_row(lines[original_txn+2],meta)
            scenario=meta['scenario_by_transaction'][original_txn]
            for variant,left,right,cv in variants(name,a,b,c,scenario):
                identity=dict(format=name,source_txn=original_txn,variant=variant,scenario=scenario)
                cases.append((identity,left,right,cv))
        directory=out/name;directory.mkdir()
        header=lines[1].split();header[0]=str(len(cases))
        inputs=directory/'inputs.txt'
        inputs.write_text('PE_VECTORS_V2\n'+' '.join(header)+'\n'+''.join(encode_row(i,a,b,c)+'\n' for i,(_,a,b,c) in enumerate(cases)))
        (directory/'golden.txt').write_text(''.join(f'{round_fp32(exact_sum((dot_product(name,a,b),decode_binary(FP32,c)))):08x}\n' for _,a,b,c in cases))
        (directory/'case-map.json').write_text(json.dumps([x[0] for x in cases],indent=2)+'\n')
        replay=['vvp',str(executable),f'+INPUT_FILE={inputs}',f'+OUTPUT_DIR={directory}',f'+RTL_ID={export}','+SCHEDULE=0',f'+TRACE_FILE={directory}/trace.csv']
        record['replay_commands'].append(replay)
        (out/'run.json').write_text(json.dumps(record,indent=2)+'\n')
        simulated=subprocess.run(replay,cwd=rtl,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        (directory/'simulation.log').write_text(simulated.stdout)
        if simulated.returncode or 'PROTOCOL_PASS' not in simulated.stdout:raise RuntimeError('diagnostic replay failed')
        results=analyze(name,cases,directory/'trace.csv')
        (directory/'analysis.json').write_text(json.dumps(results,indent=2)+'\n')
        for result in results:
            if result['variant']=='original':
                old=(ROOT/original['output_directory']/'rtl_result.txt').read_text().splitlines()[result['source_txn']]
                assert result['actual_hex']==old,('replay changed original output',result)
                old_golden=(case/'golden.txt').read_text().splitlines()[result['source_txn']]
                assert result['golden_hex']==old_golden,('replay changed original golden',result)
                assert result['fp32_steps']>2,('source transaction no longer fails its gate',result)
        all_results.extend(results)
        print(name,len(cases),'replayed; losses',dict(Counter(x['first_loss'] for x in results if x['variant']=='original')),flush=True)
    summary=dict(**record,
                 method='existing RTL hierarchy trace + exact stage-value arithmetic + counterfactual replay',
                 first_loss_counts=dict(Counter(x['first_loss'] for x in all_results if x['variant']=='original')),
                 stage_prediction_checks='All traced SubPE/PG/PE/top RTZ operations and final RNE match the intended arithmetic',
                 results=all_results)
    (out/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    executable.unlink()
    print(out/'analysis.json')


if __name__=='__main__':
    main()
