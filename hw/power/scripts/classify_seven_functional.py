#!/usr/bin/env python3
"""Seven functional areas on the same accepted dp_top mapped netlist.

Signed preparation belongs to SOP; absolute value and shift deltas belong to
alignment. Existing eight-category evidence is read-only. Decoder exponent-only
cones are extracted conservatively; shared decode/classification stays unpack.
"""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import sys

from functional_cones import Graph, load_library, recover_function, conditional_negate, signal_bits
from summarize_functional_power import ROOT, digest, write_csv, read_power

UNPACK = 'Data unpacking'
MUL = 'Mantissa & scale multiplication'
SOP = 'SOP accumulation'
EXP = 'Exponent processing'
ALIGN = 'Magnitude alignment'
NORM = 'LZD, normalization & rounding'
OTHER = 'Others'
CATEGORIES = (UNPACK, MUL, SOP, EXP, ALIGN, NORM, OTHER)


def map_row(row):
    """Semantic transfers that do not require any new cone discovery."""
    category, function, component = row['category'], row['function'], row['component']
    name = row['cell']
    if category == 'Logic control & shared logic':
        return OTHER, function
    if category == 'Magnitude shifting':
        return ALIGN, function
    if function == 'Local exponent delta cone':
        return ALIGN, function
    if category == 'Sign conversion':
        if 'absolute-value' in function:
            return ALIGN, function
        if component == 'register' and re.search(r'ff_s\d_s\d_(out_negative|c_negative)_', name):
            return ALIGN, 'Separated magnitude sign registers'
        return SOP, function
    if category == UNPACK and component == 'register' and re.search(r'ff_s0_s1_exponent_(low|upper)_', name):
        return EXP, 'S1 effective exponent banks (including Q rebias)'
    return category, function


def int_abs_targets(net, one, index):
    """A decoded INT8 branch: abs(byte) enabled only for datatype 10."""
    zero = one ^ one
    enable = one
    for bit in range(4):
        enable &= net(f'in_datatype[{bit}]') ^ (zero if 10 & (1 << bit) else one)
    raw = [net(f'in_data[{8 * index + bit}]') for bit in range(8)]
    absolute = conditional_negate(raw, raw[-1], one)
    return [bit & enable for bit in absolute]


def run_analysis(run, output):
    run.mkdir(parents=True, exist_ok=False)
    base_path = output / 'current_dp_top_sources.json'
    previous_path = output / 'current_dp_top_area_refined_sources.json'
    base = json.loads(base_path.read_text())
    previous = json.loads(previous_path.read_text())
    prior_run = ROOT / previous['report_run']
    prior_assignment = prior_run / 'refined_cell_assignment.csv'
    if digest(prior_assignment) != previous['cell_assignment_sha256']:
        raise ValueError('Previous leaf attribution changed')
    if digest(prior_run / 'lib_functions.tsv') != previous['function_table_sha256']:
        raise ValueError('Local library function export changed')
    netlist = ROOT / previous['mapped_netlist']
    if digest(netlist) != previous['mapped_netlist_sha256']:
        raise ValueError('Mapped netlist changed')
    sys.path.insert(0, str(ROOT / 'scripts'))
    from dp_power_gate import frozen_dc_source
    point = json.loads((ROOT / base['sources'][0]['original_point'] / 'point.json').read_text())
    frozen_dc_source(ROOT, point)
    original = ROOT / base['sources'][0]['supplemental_point'] / 'leaf_area.tsv'
    if digest(original) != base['sources'][0]['reports_sha256']['leaf_area.tsv']:
        raise ValueError('Mapped leaf area changed')
    leaf_rows = {r['cell']: r for r in csv.DictReader(original.open(), delimiter='\t')}
    old = {r['cell']: r for r in csv.DictReader(prior_assignment.open())}
    if old.keys() != leaf_rows.keys():
        raise ValueError('Leaf inventory mismatch')
    current = {name: dict(row, category=map_row(row)[0], function=map_row(row)[1]) for name, row in old.items()}
    library = load_library(prior_run / 'lib_functions.tsv')
    bodies = dict(re.findall(r'\bmodule\s+(\w+)\s*\((.*?)\bendmodule', netlist.read_text(), re.S))
    graphs, instances = {}, {}
    def graph(ref):
        if ref not in graphs:
            graphs[ref] = Graph(bodies[ref], library)
        return graphs[ref]
    def walk(ref, prefix):
        instances[prefix] = ref
        for child, (child_ref, _) in graph(ref).children.items():
            if child_ref in bodies:
                walk(child_ref, prefix + '/' + child if prefix else child)
    walk('dp_top', '')
    transitions = []
    proofs = []
    decoder_coverage = []
    def assign(prefix, cells, category, function, allowed):
        for cell in sorted(cells):
            name = prefix + '/' + cell
            if name not in current:
                raise ValueError('Unknown leaf: ' + name)
            if current[name]['category'] not in allowed:
                raise ValueError('Unexpected cone ownership: ' + name)
            current[name]['category'] = category
            current[name]['function'] = function
    for prefix, ref in instances.items():
        if ref.startswith('dp_global_align_'):
            g = graph(ref)
            delta = set()
            for child, (_, pins) in g.children.items():
                if '__u_global_align_shift' in child:
                    delta |= g.cone(signal_bits(g, pins['in_net']))
            exponent = g.cone(signal_bits(g, g.children['u_global_anchor_max'][1]['in_values']))
            # Only touch the previously identified exponent cone. Isolation and
            # already shared arithmetic retain their prior explicit ownership.
            owned = {cell for cell in g.cells if old[prefix + '/' + cell]['function'] == 'Global anchor correction and net shift'}
            assign(prefix, owned & delta - exponent, ALIGN, 'Global net shift amount', {EXP})
            assign(prefix, owned & exponent - delta, EXP, 'Global A_raw minus LZD before MAX', {EXP})
            assign(prefix, owned & delta & exponent, OTHER, 'Shared global exponent and shift-control cone', {EXP})
            if owned - (delta | exponent):
                raise ValueError('Global exponent partition incomplete')
        elif re.search(r'/g_decode_\d+__u_decoder$', prefix):
            g = graph(ref)
            index = int(re.search(r'/g_decode_(\d+)__u_decoder$', prefix)[1])
            exponent = g.cone(g.inputs.get('out_exponent', []))
            other_outputs = sum((g.inputs.get(port, []) for port in
                ('out_magnitude', 'out_negative', 'out_class', 'out_signaling')), [])
            other_cone = g.cone(other_outputs)
            # Exclusive effective-exponent output logic includes field routing,
            # subnormal e=1, Q bias conversion and output masking. It is not a
            # claimed measurement of the rebias adder alone.
            exclusive = exponent - other_cone
            assign(prefix, exclusive, EXP, 'Decoder effective-exponent-only cone', {UNPACK})
            abs_cells = set()
            if index < 4:
                nodes, checked = recover_function(g, lambda n, o: int_abs_targets(n, o, index))
                proofs.append(dict(instance=prefix, kind='gated_int8_abs', proofs=checked))
                abs_cells = g.cone(nodes) - exponent
                assign(prefix, abs_cells, ALIGN, 'Recovered INT8 decode absolute-value cone', {UNPACK})
            decoder_coverage.append(dict(instance=prefix, decoder_index=index,
                total_cells=len(g.cells), exponent_exclusive_cells=len(exclusive),
                exponent_shared_cells=len(exponent & other_cone),
                recovered_int_abs_cells=len(abs_cells)))
    total = 0.0
    grouped = defaultdict(lambda: dict(cell_count=0, total_um2=0.0))
    flows = defaultdict(lambda: dict(cell_count=0, total_um2=0.0))
    for name, row in current.items():
        area = float(leaf_rows[name]['area_um2'])
        if area != float(row['area_um2']):
            raise ValueError('Per-cell area changed')
        total += area
        key = row['category'], row['function'], row['component']
        if key[0] not in CATEGORIES:
            raise ValueError('Unexpected category')
        grouped[key]['cell_count'] += 1
        grouped[key]['total_um2'] += area
        key = old[name]['category'], row['category']
        flows[key]['cell_count'] += 1
        flows[key]['total_um2'] += area
    detail = [dict(category=k[0], function=k[1], component=k[2], **v,
                   area_percent=100*v['total_um2']/total) for k,v in sorted(grouped.items())]
    rows = []
    for category in CATEGORIES:
        selected = [r for r in detail if r['category'] == category]
        row = dict(category=category)
        for component in ('combinational', 'register', 'icg'):
            row[component+'_um2'] = sum(r['total_um2'] for r in selected if r['component'] == component)
        row.update(cell_count=sum(r['cell_count'] for r in selected), total_um2=sum(r['total_um2'] for r in selected))
        row['area_percent'] = 100*row['total_um2']/total
        rows.append(row)
    if sum(r['cell_count'] for r in rows) != 82502 or abs(total - previous['total_um2']) > 1e-7:
        raise ValueError('Total accounting mismatch')
    write_csv(output/'current_dp_top_area_seven.csv', rows)
    write_csv(output/'current_dp_top_area_seven_detail.csv', detail)
    write_csv(output/'current_dp_top_area_seven_transfers.csv', [dict(previous_category=k[0], category=k[1], **v) for k,v in sorted(flows.items())])
    write_csv(run/'cell_assignment.csv', list(current.values()))
    write_csv(run/'decoder_coverage.csv', decoder_coverage)
    (run/'boundary_proofs.json').write_text(json.dumps(proofs, indent=2)+'\n')
    power_rows = []
    for point in base['sources']:
        report = ROOT/point['supplemental_point']/'all_cell_net_power.rpt'
        if digest(report) != point['reports_sha256']['all_cell_net_power.rpt']:
            raise ValueError('Original cell power report changed')
        values = read_power(report, current.keys())
        grouped_power = defaultdict(lambda: defaultdict(float))
        for name, metrics in values.items():
            row = current[name]
            for metric, value in metrics.items():
                grouped_power[row['category']][metric] += value
            grouped_power[row['category']][row['component']+'_dynamic_mw'] += metrics['dynamic_mw']
        totals = {m: sum(v[m] for v in grouped_power.values()) for m in ('dynamic_mw','leakage_mw','total_mw')}
        for category in CATEGORIES:
            row = dict(format=point['format'], category=category)
            for metric in ('internal_mw','switching_mw','dynamic_mw','leakage_mw','total_mw',
                           'combinational_dynamic_mw','register_dynamic_mw','icg_dynamic_mw'):
                row[metric] = grouped_power[category][metric]
            for metric in ('dynamic','leakage','total'):
                row[metric+'_percent'] = 100*row[metric+'_mw']/totals[metric+'_mw']
            power_rows.append(row)
    write_csv(output/'current_dp_top_power_seven.csv', power_rows)
    manifest = dict(status='PASS', top='dp_top', categories=CATEGORIES, leaf_count=len(current), total_um2=total,
        source_netlist=str(netlist.relative_to(ROOT)), source_netlist_sha256=digest(netlist),
        source_eight_categories=str(previous_path.relative_to(ROOT)), source_eight_categories_sha256=digest(previous_path),
        source_original=str(base_path.relative_to(ROOT)), source_original_sha256=digest(base_path),
        report_run=str(run.relative_to(ROOT)), cell_assignment_sha256=digest(run/'cell_assignment.csv'),
        boundary_proofs_sha256=digest(run/'boundary_proofs.json'),
        additional_sat_proved_bits=sum(len(p['proofs']) for p in proofs),
        decoder_instances=len(decoder_coverage),
        policy='Signed preparation and signed payload registers to SOP; abs and shift amounts to alignment; MAX/A_raw/A_raw-z and effective exponent banks to exponent processing.',
        decoder_policy='Only effective-exponent-exclusive cones moved; shared extraction/classification remains unpack. These are not isolated rebias-adder measurements.',
        limitation='Unseparable mixed cones retain their recorded ownership; no proportional allocation or resynthesis.',
        scripts_sha256={p.name:digest(p) for p in (Path(__file__),Path(__file__).with_name('functional_cones.py'))})
    (output/'current_dp_top_area_seven_sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (run/'manifest.json').write_text(json.dumps(dict(status='complete',no_compile=True,
        referenced_by='paper/data/H16Q32E64_area/current_dp_top_area_seven_sources.json'),indent=2)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True, help='A new local output directory')
    parser.add_argument('--output', type=Path, default=ROOT/'paper/data/H16Q32E64_area')
    args = parser.parse_args()
    run_analysis(args.run.resolve(), args.output.resolve())
