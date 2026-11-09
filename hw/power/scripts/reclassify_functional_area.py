#!/usr/bin/env python3
"""Refine the accepted dp_top area into eight exclusive functional categories.

Mapped gates are never resynthesized. Named cut points and SAT-recovered pair /
absolute-value nodes partition local cones; cross-function and unrecovered gates
remain explicitly identified in Logic control & shared logic.
"""
import argparse
from collections import defaultdict
import csv
from functools import lru_cache
import json
from pathlib import Path
import re
from functional_cones import Graph, load_library, recover_pair, recover_function, conditional_negate, signal_bits
from summarize_functional_power import ROOT, classify, digest, write_csv, read_power

UNPACK='Data unpacking'; MUL='Mantissa & scale multiplication'; ADD='SOP accumulation'
EXP='Exponent processing'; SHIFT='Magnitude shifting'; SIGN='Sign conversion'
NORM='LZD, normalization & rounding'; CONTROL='Logic control & shared logic'
CATEGORIES=(UNPACK,MUL,ADD,EXP,SHIFT,SIGN,NORM,CONTROL)


def basic(name,sequential):
    category,function,component=classify(name,sequential)
    if component=='icg':return CONTROL,'Clock gating',component
    if sequential:
        m=re.search(r'ff_s\d_s\d_(.*?)_ff_storage_out_q_reg',name);field=m[1] if m else ''
        if field in ('leaf_lower','leaf_upper','leaves','negative','out_negative','c_negative'):
            return SIGN,'Signed payload and sign pipeline registers',component
        if field in ('anchor_s2','anchor_s3','out_anchor','common_s6','common_s7'):
            return EXP,'Anchor and exponent pipeline registers',component
        if field=='active':return CONTROL,'Product active registers',component
    if '/u_lane_exponent_max/' in name or '/u_group_exponent_max/' in name or '/u_global_anchor_max/' in name:
        return EXP,'Exponent MAX trees',component
    if '__u_local_align_shift/' in name or '__u_global_align_shift/' in name:
        return SHIFT,'Dedicated RTZ or bidirectional shift core',component
    if '/u_local_alignment/' in name or name.startswith('u_global_alignment/'):
        return CONTROL,'Unresolved mixed alignment logic',component
    mapping={'Addition & accumulation':ADD,'Exponent arithmetic':EXP,
             'Alignment & exponent selection':CONTROL,'Others':CONTROL}
    return mapping.get(category,category),function,component


def discover_cones(netlist,library):
    """Discover direct-parent arithmetic cones on a specified mapped netlist.

    Reused for later accepted snapshots; never reuse U-number ownership across
    netlists. Returned ownership is eight-category intermediate data.
    """
    bodies=dict(re.findall(r'\bmodule\s+(\w+)\s*\((.*?)\bendmodule',netlist.read_text(),re.S))
    graphs={}
    def graph(ref):
        if ref not in graphs:graphs[ref]=Graph(bodies[ref],library)
        return graphs[ref]
    instances={}
    def walk(ref,prefix):
        instances[prefix]=ref
        for child,(childref,_) in graph(ref).children.items():
            if childref in bodies:walk(childref,prefix+'/'+child if prefix else child)
    walk('dp_top','')
    assigned={}; proofs=[]; overlap=set(); details=defaultdict(int)
    def record(prefix,g,sets):
        for cell in g.cells:
            owners=[(c,f) for c,f,cells in sets if cell in cells]
            if not owners:continue
            name=prefix+'/'+cell if prefix else cell
            categories={c for c,_ in owners}
            if len(categories)>1:
                assigned[name]=(CONTROL,'Shared cone across functional boundaries','combinational');overlap.add(name)
            else:assigned[name]=(owners[0][0],owners[0][1],'combinational')
    def inputs_of(g,child,port):
        return signal_bits(g,g.children[child][1].get(port,''))
    def d_inputs(g,pattern):
        return [pins['D'] for child,(_,pins) in g.children.items() if re.search(pattern,child) and 'D' in pins]
    for prefix,ref in instances.items():
        if not (ref.startswith('dp_lane_align_') or ref.startswith('dp_global_align_') or
                ref.startswith('dp_group_LOCAL_') or ref.startswith('dp_lane_LOCAL_') or
                ref.startswith('dp_fp32_round_') or ref.startswith('dp_c_unpack_') or
                ref.startswith('dp_lane_unpack_')):continue
        g=graph(ref); sets=[]
        if ref.startswith('dp_lane_align_'):
            recovered,checked=recover_pair(g)
            proofs.append(dict(instance=prefix,kind='pair',proofs=checked))
            signed_inputs=set(); sums=set(); abs_cells=set()
            # Classify single-operand preprocessing separately from cells combining
            # the two pair operands. This also handles factored input negation.
            @lru_cache(None)
            def support(net):
                if net not in g.nodes:return frozenset([net])
                _,ast,pins=g.nodes[net]
                def visit(a):
                    if a[0]=='pin':return support(pins[a[1]]) if a[1] in pins else frozenset()
                    return frozenset().union(*(visit(c) for c in a[1:]))
                return visit(ast)
            pair_control=set()
            for i in range(4):
                targets=recovered[f'{i}_pair_sum']+recovered[f'{i}_raw_sum']
                sum_cone=g.cone(targets)
                for cell in sum_cone:
                    output_nets=[n for n,(owner,_,_) in g.nodes.items() if owner==cell]
                    deps=frozenset().union(*(support(n) for n in output_nets))
                    operands={int(m[1])//22 for n in deps if (m:=re.fullmatch(r'in_products\[(\d+)\]',n))}
                    if not operands:pair_control.add(cell)
                    elif len(operands)==1:signed_inputs.add(cell)
                    else:sums.add(cell)
                abs_cells |= g.cone(recovered[f'{i}_pair_abs']+recovered[f'{i}_raw_abs'])-sum_cone
            pre=set();delta=set()
            for child in g.children:
                if '__u_local_align_shift' in child:
                    pre |= g.cone(inputs_of(g,child,'in_magnitude'))
                    delta |= g.cone(inputs_of(g,child,'in_shift'))
            pair_all=signed_inputs|sums|abs_cells|pair_control
            # Signed leaves are after the shift boundary. Shared pre-shift cells
            # remain upstream, not charged twice to sign restoration.
            restore=g.cone(g.inputs['out_leaves'])-(pre|delta|pair_all)
            sets=[(SIGN,'E pair operand sign preparation',signed_inputs),
                  (ADD,'SAT-recovered E pair sum cones',sums),
                  (SIGN,'E pair absolute-value cones',abs_cells),
                  (SIGN,'Post-shift complement restoration',restore),
                  (EXP,'Local exponent delta cone',delta-pair_all),
                  (CONTROL,'Pair enable and shared control',pair_control)]
            details['pair_bits_proved']+=len(checked)
        elif ref.startswith('dp_global_align_'):
            exponent=set(); magnitude=set()
            for child in g.children:
                if '__u_global_align_shift' in child:
                    exponent |= g.cone(inputs_of(g,child,'in_net'))
                    magnitude |= g.cone(inputs_of(g,child,'in_magnitude'))
            if 'u_global_anchor_max' in g.children:
                exponent |= g.cone(inputs_of(g,'u_global_anchor_max','in_values'))
            bypass=set()
            for i in range(5):
                shifted=inputs_of(g,f'g_source_{i}__u_global_align_shift','out_magnitude')
                def select_builder(n,o):
                    mode=n('in_integer')
                    return [(n(f'in_magnitude[{39*i+b}]') & mode) | (n(shifted[b]) & (mode^o)) for b in range(39)]
                names,checked=recover_function(g,select_builder)
                proofs.append(dict(instance=prefix,kind=f'integer_bypass_{i}',proofs=checked))
                bypass |= g.cone(names)
            bypass -= exponent|magnitude
            restore=g.cone(g.inputs['out_leaves'])-(exponent|magnitude|bypass)
            sets=[(EXP,'Global anchor correction and net shift',exponent),
                  (SIGN,'Global complement restore after recovered bypass boundary',restore),
                  (CONTROL,'Recovered integer bypass selection',bypass),
                  (CONTROL,'Global active isolation and shared selection',magnitude)]
        elif ref.startswith('dp_group_LOCAL_'):
            names,checked=recover_function(g,lambda n,o:conditional_negate([n(f'group_sum[{i}]') for i in range(32)],n('group_sum[31]'),o))
            abscone=g.cone(names)
            proofs.append(dict(instance=prefix,kind='group_abs',proofs=checked))
            anchor=g.cone(d_inputs(g,r'ff_s4_s5_out_anchor_')+d_inputs(g,r'ff_s1_s2_scale_exp_'))
            sets=[(SIGN,'Group absolute-value cone',abscone),
                  (EXP,'Group scale exponent and anchor correction',anchor-abscone)]
        elif ref.startswith('dp_lane_unpack_'):
            sets=[(SIGN,'Product sign XOR and sign routing',g.cone(g.inputs.get('out_product_negative',[])))]
        elif ref.startswith('dp_lane_LOCAL_'):
            sets=[(SIGN,'Product sign generation',g.cone(d_inputs(g,r'ff_s1_s2_negative_')))]
        elif ref.startswith('dp_fp32_round_'):
            names,checked=recover_function(g,lambda n,o:conditional_negate([n(f'in_sum[{i}]') for i in range(43)],n('in_sum[42]'),o))
            proofs.append(dict(instance=prefix,kind='output_abs',proofs=checked))
            sets=[(SIGN,'Final sum absolute-value cone',g.cone(names))]
        elif ref.startswith('dp_c_unpack_'):
            # C float decode and INT32 conditional abs share output selection.
            # Only exact, unconstrained internal abs functions are recovered.
            names,checked=recover_function(g,lambda n,o:conditional_negate([n(f'in_data[{i}]') for i in range(32)],n('in_data[31]'),o))
            proofs.append(dict(instance=prefix,kind='c_int_abs',proofs=checked))
            sets=[(SIGN,'C INT32 absolute-value cone',g.cone(names))]
        record(prefix,g,sets)
        print(prefix or 'top','refined',len(assigned),flush=True)
    return assigned,proofs,overlap


def refine(run,output):
    source=json.loads((output/'current_dp_top_sources.json').read_text())
    original=ROOT/source['sources'][0]['supplemental_point']/'leaf_area.tsv'
    assert digest(original)==source['sources'][0]['reports_sha256']['leaf_area.tsv']
    netlist=ROOT/source['dc_run']/'netlist/dp_top_mapped.v'
    # Independent frozen source + mapped artifact acceptance, no current-RTL substitution.
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from dp_power_gate import frozen_dc_source
    point=json.loads((ROOT/source['sources'][0]['original_point']/'point.json').read_text())
    frozen_dc_source(ROOT,point)
    library=load_library(run/'lib_functions.tsv')
    assigned,proofs,overlap=discover_cones(netlist,library)
    leaves={r['cell']:r for r in csv.DictReader(original.open(),delimiter='\t')}
    if not assigned.keys()<=leaves.keys():raise ValueError('Unknown refined cells')
    totals=defaultdict(lambda:defaultdict(float)); counts=defaultdict(int);raw=[]
    for name,row in leaves.items():
        key=assigned.get(name,basic(name,row['sequential']=='true'))
        area=float(row['area_um2']);totals[key]['area_um2']+=area;counts[key]+=1
        raw.append(dict(cell=name,category=key[0],function=key[1],component=key[2],area_um2=area))
    total=sum(float(r['area_um2']) for r in leaves.values())
    detail=[dict(category=k[0],function=k[1],component=k[2],cell_count=counts[k],total_um2=v['area_um2'],area_percent=100*v['area_um2']/total) for k,v in sorted(totals.items())]
    rows=[]
    for cat in CATEGORIES:
        selected=[r for r in detail if r['category']==cat];row=dict(category=cat)
        for comp in ('combinational','register','icg'):row[comp+'_um2']=sum(r['total_um2'] for r in selected if r['component']==comp)
        row.update(cell_count=sum(r['cell_count'] for r in selected),total_um2=sum(r['total_um2'] for r in selected))
        row['area_percent']=row['total_um2']/total*100;rows.append(row)
    assert sum(r['cell_count'] for r in rows)==len(leaves)
    assert abs(sum(r['total_um2'] for r in rows)-total)<1e-7
    write_csv(output/'current_dp_top_area_refined.csv',rows)
    write_csv(output/'current_dp_top_area_refined_detail.csv',detail)
    write_csv(run/'refined_cell_assignment.csv',raw)
    (run/'boundary_proofs.json').write_text(json.dumps(proofs,indent=2)+'\n')
    # Reuse the exact audited per-cell SAIF reports: only attribution changes.
    assignments={r['cell']:(r['category'],r['component']) for r in raw}
    power_rows=[]
    for point in source['sources']:
        path=ROOT/point['supplemental_point']/'all_cell_net_power.rpt'
        assert digest(path)==point['reports_sha256']['all_cell_net_power.rpt']
        powers=read_power(path,leaves.keys())
        grouped=defaultdict(lambda:defaultdict(float))
        for name,values in powers.items():
            cat,comp=assignments[name]
            for metric,value in values.items():grouped[cat][metric]+=value
            grouped[cat][comp+'_dynamic_mw']+=values['dynamic_mw']
        sums={metric:sum(values[metric] for values in grouped.values()) for metric in ('dynamic_mw','leakage_mw','total_mw')}
        for cat in CATEGORIES:
            row=dict(format=point['format'],category=cat)
            for metric in ('internal_mw','switching_mw','dynamic_mw','leakage_mw','total_mw',
                           'combinational_dynamic_mw','register_dynamic_mw','icg_dynamic_mw'):
                row[metric]=grouped[cat][metric]
            for metric in ('dynamic','leakage','total'):row[metric+'_percent']=row[metric+'_mw']/sums[metric+'_mw']*100
            power_rows.append(row)
    write_csv(output/'current_dp_top_power_refined.csv',power_rows)
    summary=dict(status='PASS',categories=list(CATEGORIES),leaf_count=len(leaves),total_um2=total,
                 mapped_netlist=str(netlist.relative_to(ROOT)),mapped_netlist_sha256=digest(netlist),
                 report_run=str(run.relative_to(ROOT)),function_table_sha256=digest(run/'lib_functions.tsv'),
                 boundary_proofs_sha256=digest(run/'boundary_proofs.json'),
                 cell_assignment_sha256=digest(run/'refined_cell_assignment.csv'),
                 original_sources_sha256=digest(output/'current_dp_top_sources.json'),
                 pair_sum_recovered_bits=sum(sum(item[1]=='pair_sum' for item in p['proofs']) for p in proofs if p['kind']=='pair'),
                 methodology='1024 deterministic random patterns select candidates; every accepted node/inversion is proved with Z3 (unsat miter). Constant targets excluded.',
                 sat_proven_bits=sum(len(p['proofs']) for p in proofs),overlap_cells=len(overlap),
                 policy='Eight exclusive categories; registers follow stored producer function; ICG in control.',
                 limitation='Unrecovered or fused arithmetic and format selection remain explicitly in control/shared; no proportional allocation.',
                 scripts_sha256={p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('functional_cones.py'),Path(__file__).with_name('export_functional_cones.tcl'),Path(__file__).with_name('summarize_functional_power.py')]})
    (output/'current_dp_top_area_refined_sources.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'paper/data/H16Q32E64_area')
    args=parser.parse_args();refine(args.run.resolve(),args.output.resolve())
