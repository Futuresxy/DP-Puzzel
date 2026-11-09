#!/usr/bin/env python3
"""Apply the agreed seven functional categories to the fixed-atom dp_top netlist.

Recompute all cones on the new netlist; do not transfer old cell names or powers.
Raw library functions, physical assignments and SAT proofs remain local.
"""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import sys

from functional_cones import Graph, load_library, recover_function, signal_bits
from reclassify_functional_area import basic, discover_cones
from functional_mode_cones import mode_cone
from classify_seven_functional import map_row, int_abs_targets, CATEGORIES, UNPACK, EXP, ALIGN, OTHER
from summarize_functional_power import ROOT, digest, write_csv


def classify(report, output):
    source=json.loads((report/'source.json').read_text())
    if source['status']!='PASS' or not source['no_compile'] or not source['no_power']:
        raise ValueError('Expected accepted read-only area export')
    run=ROOT/'hw/dc_syn/runs'/source['source_run']
    sys.path.insert(0,str(ROOT/'hw/dc_syn/scripts'))
    from run_dc import verify_inputs
    verify_inputs(run)
    summary=json.loads((run/'summary.json').read_text())
    if not summary['flow_pass'] or summary['parameters']!={'K_FP16':16,'LOCAL_W':28,'GLOBAL_W':40}:
        raise ValueError('Expected accepted K16/28/40 snapshot')
    for name,expected in source['files_sha256'].items():
        if digest(report/name)!=expected:raise ValueError('Changed export: '+name)
    netlist=run/'netlist/dp_top_mapped.v'
    for name,expected in source['source_hashes'].items():
        if digest(run/'netlist'/name)!=expected:raise ValueError('Changed mapped artifact')
    leaf_rows=list(csv.DictReader((report/'leaf_area.tsv').open(),delimiter='\t'))
    leaves={r['cell']:r for r in leaf_rows}
    if len(leaves)!=len(leaf_rows):raise ValueError('Duplicate physical leaf')
    library=load_library(report/'lib_functions.tsv')
    assigned,proofs,overlap=discover_cones(netlist,library)
    if not assigned.keys()<=leaves.keys():raise ValueError('Unknown cone leaf')
    current={}
    for name,row in leaves.items():
        category,function,component=assigned.get(name,basic(name,row['sequential']=='true'))
        intermediate=dict(cell=name,category=category,function=function,component=component)
        category,function=map_row(intermediate)
        current[name]=dict(intermediate,category=category,function=function,area_um2=float(row['area_um2']))
    bodies=dict(re.findall(r'\bmodule\s+(\w+)\s*\((.*?)\bendmodule',netlist.read_text(),re.S))
    graphs={};instances={}
    def graph(ref):
        if ref not in graphs:graphs[ref]=Graph(bodies[ref],library)
        return graphs[ref]
    def walk(ref,prefix):
        instances[prefix]=ref
        for name,(child,_) in graph(ref).children.items():
            if child in bodies:walk(child,prefix+'/'+name if prefix else name)
    walk('dp_top','')
    def assign(prefix,cells,category,function,allowed):
        for cell in cells:
            name=prefix+'/'+cell
            if name not in current or current[name]['category'] not in allowed:
                raise ValueError('Unexpected cone owner: '+name)
            current[name].update(category=category,function=function)
    decoder_coverage=[]
    for prefix,ref in instances.items():
        g=graph(ref)
        if ref.startswith('dp_global_align_'):
            delta=set()
            for child,(_,pins) in g.children.items():
                if '__u_global_align_shift' in child:delta|=g.cone(signal_bits(g,pins['in_net']))
            exponent=g.cone(signal_bits(g,g.children['u_global_anchor_max'][1]['in_values']))
            owned={cell for cell in g.cells if current[prefix+'/'+cell]['function']=='Global anchor correction and net shift'}
            assign(prefix,(owned&delta)-exponent,ALIGN,'Global net shift amount',{EXP})
            assign(prefix,(owned&exponent)-delta,EXP,'Global A_raw minus LZD before MAX',{EXP})
            assign(prefix,owned&delta&exponent,OTHER,'Shared global exponent and shift-control cone',{EXP})
            if owned-(delta|exponent):raise ValueError('Incomplete global partition')
        elif ref.startswith('dp_unpack_atom_'):
            atom=int(re.search(r'ATOM_INDEX(\d+)',ref)[1])
            exponent=g.cone(g.inputs['out_exponents'])
            others=g.cone(sum((g.inputs[port] for port in ('out_mantissas','out_signs','out_classes','out_signaling')),[]))
            exclusive=exponent-others
            assign(prefix,exclusive,EXP,'Decoder effective-exponent-only cone',{UNPACK})
            abs_cells=set()
            for slot in range(2):
                byte_index=2*atom+slot
                nodes,checked=recover_function(g,lambda n,o:int_abs_targets(n,o,byte_index))
                proofs.append(dict(instance=prefix,kind=f'gated_int8_abs_byte_{byte_index}',proofs=checked))
                abs_cells|=g.cone(nodes)-exponent
            assign(prefix,abs_cells,ALIGN,'Recovered INT8 decode absolute-value cone',{UNPACK})
            # Fused INT8 abs may have no standalone gated-abs node. Only assign
            # magnitude gates exclusive to INT8 and not used by other outputs;
            # shared decode/selection stays unpack. No proportional allocation.
            int_mode=mode_cone(g,g.inputs['out_mantissas'],10)
            other_modes=set().union(*(mode_cone(g,g.inputs['out_mantissas'],mode) for mode in range(10)))
            other_fields=g.cone(sum((g.inputs[p] for p in ('out_exponents','out_signs','out_classes','out_signaling')),[]))
            int_exclusive=int_mode-other_modes-other_fields-abs_cells
            assign(prefix,int_exclusive,ALIGN,'INT8-exclusive magnitude logic (abs and dedicated routing)',{UNPACK})
            decoder_coverage.append(dict(instance=prefix,atom=atom,total_cells=len(g.cells),
                exponent_exclusive_cells=len(exclusive),exponent_shared_cells=len(exponent&others),
                recovered_int_abs_cells=len(abs_cells),int_exclusive_magnitude_cells=len(int_exclusive)))
    if len(decoder_coverage)!=32:raise ValueError('Expected 32 A/B atoms')
    # Independent hierarchy check on the newly exported physical leaves.
    ancestors=defaultdict(float)
    for name,row in current.items():
        ancestors['dp_top']+=row['area_um2']
        parts=name.split('/')
        for i in range(1,len(parts)):ancestors['/'.join(parts[:i])]+=row['area_um2']
    compared=[]
    for line in (run/'reports/area_hierarchy.rpt').read_text().splitlines():
        f=line.split()
        if not f or f[0] not in ancestors:continue
        difference=ancestors[f[0]]-float(f[1])
        if abs(difference)>0.0005:raise ValueError('Hierarchy mismatch: '+f[0])
        compared.append(dict(instance=f[0],leaf_area_um2=ancestors[f[0]],report_area_um2=float(f[1]),difference_um2=difference))
    if len(compared)!=len(ancestors):raise ValueError('Missing hierarchy evidence')
    total=ancestors['dp_top']
    if abs(total-summary['area']['total_cell_area_um2'])>0.0005:raise ValueError('Total area mismatch')
    grouped=defaultdict(lambda:dict(cell_count=0,total_um2=0.0))
    for row in current.values():
        key=row['category'],row['function'],row['component']
        if key[0] not in CATEGORIES:raise ValueError('Unexpected category')
        grouped[key]['cell_count']+=1;grouped[key]['total_um2']+=row['area_um2']
    detail=[dict(category=k[0],function=k[1],component=k[2],**v,area_percent=100*v['total_um2']/total) for k,v in sorted(grouped.items())]
    rows=[]
    for category in CATEGORIES:
        selected=[r for r in detail if r['category']==category]
        r=dict(category=category)
        for component in ('combinational','register','icg'):
            r[component+'_um2']=sum(x['total_um2'] for x in selected if x['component']==component)
        r.update(cell_count=sum(x['cell_count'] for x in selected),total_um2=sum(x['total_um2'] for x in selected))
        r['area_percent']=100*r['total_um2']/total;rows.append(r)
    if sum(r['cell_count'] for r in rows)!=len(leaves) or abs(sum(r['total_um2'] for r in rows)-total)>1e-7:
        raise ValueError('Accounting mismatch')
    output.mkdir(parents=True,exist_ok=True)
    write_csv(output/'fixed_unpack_area_seven.csv',rows)
    write_csv(output/'fixed_unpack_area_seven_detail.csv',detail)
    write_csv(report/'cell_assignment.csv',list(current.values()))
    write_csv(report/'decoder_coverage.csv',decoder_coverage)
    write_csv(report/'hierarchy_crosscheck.csv',compared)
    (report/'boundary_proofs.json').write_text(json.dumps(proofs,indent=2)+'\n')
    old={r['category']:r for r in csv.DictReader((output/'current_dp_top_area_seven.csv').open())}
    write_csv(output/'fixed_unpack_area_seven_comparison.csv',[
        dict(category=r['category'],baseline_um2=float(old[r['category']]['total_um2']),new_um2=r['total_um2'],
             delta_um2=r['total_um2']-float(old[r['category']]['total_um2']),
             baseline_percent=float(old[r['category']]['area_percent']),new_percent=r['area_percent']) for r in rows])
    metadata=dict(status='PASS',dc_run=source['source_run'],export_id=source['export_id'],report_run=str(report.relative_to(ROOT)),
        mapped_netlist_sha256=digest(netlist),source_export_sha256=digest(report/'source.json'),
        leaf_count=len(leaves),hierarchy_rows=len(compared),total_um2=total,official_total_um2=summary['area']['total_cell_area_um2'],
        max_hierarchy_difference_um2=max(abs(r['difference_um2']) for r in compared),
        sat_proved_bits=sum(len(p['proofs']) for p in proofs),overlap_cells=len(overlap),atom_instances=len(decoder_coverage),
        categories=CATEGORIES,policy='Same seven ownership rules; recompute cones and proofs on fixed-unpack mapped netlist; exponent-exclusive atom cone to exponent, recovered gated INT8 abs to alignment; INT8-only magnitude dependencies to alignment; shared decode remains unpack.',
        limitation='Fused/unrecovered logic retains documented ownership or Others. Not standalone operator area. No old power data mapped to this netlist.',
        evidence_sha256={n:digest(report/n) for n in ('cell_assignment.csv','boundary_proofs.json','decoder_coverage.csv','hierarchy_crosscheck.csv')},
        scripts_sha256={p.name:digest(p) for p in (Path(__file__),Path(__file__).with_name('reclassify_functional_area.py'),Path(__file__).with_name('functional_cones.py'),Path(__file__).with_name('classify_seven_functional.py'),Path(__file__).with_name('functional_mode_cones.py'))})
    (output/'fixed_unpack_area_seven_sources.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (report/'manifest.json').write_text(json.dumps(dict(status='complete',no_compile=True,no_power=True,referenced_by='paper/data/H16Q32E64_area/fixed_unpack_area_seven_sources.json'),indent=2)+'\n')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'paper/data/H16Q32E64_area')
    args=parser.parse_args();classify(args.report.resolve(),args.output.resolve())
