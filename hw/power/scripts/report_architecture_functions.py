#!/usr/bin/env python3
"""Seven exclusive major-function accounts for audited DP netlists and SAIF.

Recompute ownership on each mapped netlist. Major hierarchy and named register
fields define ownership; direct-parent cones split delta/MAX/sign/abs logic.
Cross-category cone overlap stays in Others. No proportional residual allocation.
Physical cell names and library functions remain in ignored reporting runs.
"""
import argparse
from collections import defaultdict
from decimal import Decimal
import csv
import json
import math
from pathlib import Path
import re
import sys

from functional_cones import Graph, load_library, signal_bits
from summarize_functional_power import ROOT, POWER_ROW, digest, read_power, write_csv
from run_power import execute, save

sys.path.insert(0, str(ROOT / 'scripts'))
from dp_power_gate import frozen_dc_source

UNPACK = 'Data unpacking'
MUL = 'Mantissa & scale multiplication'
ADD = 'SOP accumulation'
ALIGN = 'Alignment & shift delta'
EXP = 'Exponent processing'
NORM = 'LZD, normalization & rounding'
OTHER = 'Others'
CATEGORIES = (UNPACK, MUL, ADD, ALIGN, EXP, NORM, OTHER)


def register_owner(name):
    match = re.search(r'ff_s\d+_s\d+_(.*?)_ff_storage', name)
    field = match[1] if match else ''
    if re.match(r'(?:a_|b_)?(?:mantissa|sign)_s1|(?:ea|eb|sa|sb)(?:_|$)|nan_s1|c_(?:magnitude|negative|anchor|special|compare)', field):
        return UNPACK, 'Decoded input payload registers'
    if re.search(r'exponent|scale_exp|anchor|compare_exp|common_s|group_max', field):
        return EXP, 'Exponent and anchor pipeline registers'
    if re.search(r'product|coeff', field) and not re.search(r'all_negative|active', field):
        return MUL, 'Product and scale coefficient registers'
    if field == 'out_magnitude':
        return MUL, 'S5 scaled or bypassed group magnitude registers'
    if re.match(r'leaf_|leaves|base_leaves|extension_leaves|c_leaf|magnitude_s4|shift_s', field):
        return ALIGN, 'Aligned operands or group absolute magnitude registers'
    if re.match(r'pairs|sop|fused_sum|out_sop|sum$|out_negative|negative_s4', field):
        return ADD, 'Pair and accumulation registers'
    if re.match(r'out_z|c_z|out_d$', field):
        return NORM, 'Leading-count and final result registers'
    if field == 'c_raw':
        return OTHER, 'Raw C transport registers'
    return OTHER, 'Control, transport and shared registers'


def hierarchy_owner(ref):
    if re.match(r'dp_(?:lane_unpack|lane_operand_unpack|operand_unpack|unpack_atom|scale_unpack|c_unpack)', ref):
        return UNPACK, 'A/B, scale or C decode and decode registers'
    if re.match(r'dp_(?:mul_unsigned|mantissa_bank|mantissa_mul|scale_multiply)', ref):
        return MUL, 'Element and scale mantissa multiplication'
    if re.match(r'dp_(?:exponent_|max_tree)', ref):
        return EXP, 'Exponent addition and MAX reduction'
    if re.match(r'dp_(?:rtz_shift|bidir_shift|lane_e_shift)', ref):
        return ALIGN, 'Magnitude alignment or local HiF4 scaling'
    if re.match(r'dp_(?:sum_tree|final_csa_sum|mixed_csa_sum|csa)', ref):
        return ADD, 'Pair, lane, group and global reduction trees'
    if re.match(r'dp_(?:lzd|fp32_round)', ref):
        return NORM, 'Leading detection, normalization and rounding'
    return None


def assign_cells(netlist, library_path, top, leaves):
    bodies = dict(re.findall(r'\bmodule\s+(\w+)\s*\((.*?)\bendmodule', netlist.read_text(), re.S))
    library = load_library(library_path)
    graphs = {}
    instances = {}
    owners = {}

    def graph(ref):
        if ref not in graphs:
            graphs[ref] = Graph(bodies[ref], library)
        return graphs[ref]

    def walk(ref, prefix, inherited=None):
        owner = inherited or hierarchy_owner(ref)
        instances[prefix] = ref
        owners[prefix] = owner
        for child, (childref, _) in graph(ref).children.items():
            if childref in bodies:
                walk(childref, prefix + '/' + child if prefix else child, owner)

    walk(top, '')
    assigned = {}
    for name, row in leaves.items():
        prefix = name.rpartition('/')[0]
        component = 'register' if row['sequential'] == 'true' else 'combinational'
        if 'clk_gate_' in name:
            category, function, component = OTHER, 'Clock gating cells', 'icg'
        else:
            category, function = owners.get(prefix) or (
                register_owner(name) if component == 'register' else
                (OTHER, 'Shared control and unnamed inline logic'))
        assigned[name] = dict(category=category, function=function, component=component,
                              area_um2=float(row['area_um2']))

    cone_audit = []
    for prefix, ref in instances.items():
        if owners[prefix] is not None or ref.startswith('SNPS_'):
            continue
        g = graph(ref)
        cones = defaultdict(set)
        functions = {}

        def add(category, function, targets):
            cones[category].update(g.cone(targets))
            functions[category] = function

        # Logic driving named datapath DFFs is attributed with its destination.
        # State/control DFF cones stay Others; crossing sequential boundaries is
        # impossible because library functions exclude sequential cells.
        for child, (_, pins) in g.children.items():
            if 'ff_storage' in child and 'D' in pins:
                category, function = register_owner(child)
                if category != OTHER:
                    add(category, function + ' input logic', [pins['D']])

        is_align = ref.startswith(('dp_lane_align_', 'dp_global_align_', 'dp_mixed_global_align_'))
        if ref.startswith('dp_qe_product_bank'):
            add(EXP, 'QE element exponent addition', g.inputs.get('out_exponents', []))
        for child, (childref, pins) in g.children.items():
            if childref.startswith('dp_max_tree'):
                add(EXP, 'Active exponent selection and MAX input logic', signal_bits(g, pins.get('in_values', '')))
            if childref.startswith(('dp_rtz_shift', 'dp_bidir_shift')):
                for port in ('in_shift', 'in_net', 'in_magnitude'):
                    add(ALIGN, 'Shift delta and magnitude preparation', signal_bits(g, pins.get(port, '')))
            if childref.startswith('dp_sum_tree') and ref.startswith('dp_lane_e_'):
                add(ADD, 'E signed product preparation and pair input logic', signal_bits(g, pins.get('in_values', '')))
            if childref.startswith('dp_mul_unsigned') and ref.startswith('dp_qe_product_bank'):
                for port in ('in_a', 'in_b'):
                    add(MUL, 'QE mantissa routing and multiplier isolation', signal_bits(g, pins.get(port, '')))
            if childref.startswith('dp_scale_multiply'):
                # Abs is an alignment preparation operation; the scale
                # coefficient belongs to the multiply input, with shared gates
                # separated by the overlap check below.
                for port in ('in_magnitude',):
                    add(ALIGN, 'Group absolute-value preparation', signal_bits(g, pins.get(port, '')))
                for port in ('in_coefficient',):
                    add(MUL, 'Scale coefficient selection', signal_bits(g, pins.get(port, '')))
        if is_align:
            # Restore signed values after shift; E pair bypass belongs to SOP.
            targets = g.inputs.get('out_leaves', [])
            upstream = set().union(*cones.values()) if cones else set()
            cones[ADD].update(g.cone(targets) - upstream)
            functions[ADD] = 'Signed leaves, E pair and bypass preparation'
            add(EXP, 'Common exponent output selection', g.inputs.get('out_anchor', []))
        if ref.startswith(('dp_group_', 'dp_group_e_', 'dp_group_qe_')):
            # Named absolute_sop may survive as a cutpoint. Only its direct
            # combinational cone is counted; upstream group tree is a module.
            absolute = g.cone(g.inputs.get('absolute_sop', []))
            if absolute:
                for category in cones:
                    cones[category].difference_update(absolute)
                cones[ALIGN].update(absolute)
                functions[ALIGN] = 'Group absolute-value preparation'
        overlap = 0
        for cell in g.cells:
            name = prefix + '/' + cell if prefix else cell
            if name not in assigned:
                raise ValueError('Cone cell missing from physical inventory: ' + name)
            selected = [category for category, cells in cones.items() if cell in cells]
            if len(selected) == 1:
                category = selected[0]
                assigned[name].update(category=category, function=functions[category])
            elif len(selected) > 1:
                overlap += 1
                assigned[name].update(category=OTHER, function='Shared logic crossing functional boundaries')
        if cones:
            cone_audit.append(dict(instance=prefix, reference=ref, overlap_cells=overlap,
                                   category_cells={k: len(v) for k, v in cones.items()}))
    return assigned, cone_audit


def displayed_rounding_bounds(path, names):
    """Bound loss from the actual decimal precision printed per physical cell.

    report_default_significant_digits does not control report_power -cell.
    The tool prints exact zero as 0.0000 and small nonzero values in scientific
    notation; zero therefore contributes no display uncertainty. A fixed
    percentage tolerance would reject small designs unfairly. Keep
    the unadjusted residual and test it against summed half-last-digit bounds.
    """
    bounds = dict(internal_mw=0., switching_mw=0., leakage_mw=0.)
    for line in path.read_text().splitlines():
        match = POWER_ROW.match(line)
        if not match or match[1] not in names:
            continue
        for key, column, factor in [('internal_mw', 2, 1.), ('switching_mw', 3, 1.), ('leakage_mw', 5, 1e-6)]:
            value = Decimal(match[column])
            if value:
                bounds[key] += .5 * 10. ** value.as_tuple().exponent * factor
    bounds['dynamic_mw'] = bounds['internal_mw'] + bounds['switching_mw']
    bounds['total_mw'] = bounds['dynamic_mw'] + bounds['leakage_mw']
    return bounds


def check_point(point_dir):
    point = json.loads((point_dir / 'point.json').read_text())
    audit = json.loads((point_dir / 'power_audit.json').read_text())
    if audit['status'] != 'PASS':
        raise ValueError('Power point not accepted')
    frozen_dc_source(ROOT, point)
    for name, expected in audit['artifacts_sha256'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('Changed accepted power artifact: ' + name)
    return point, audit


def export(point_dir, report_dir, machine_path):
    point, audit = check_point(point_dir)
    report_dir.mkdir(parents=True, exist_ok=False)
    save(report_dir / 'source.json', dict(point=str(point_dir.relative_to(ROOT)), audit=audit))
    machine = json.loads(machine_path.read_text())
    # Explicit original config; no compile or new activity is performed here.
    config = point_dir / 'config.tcl'
    wrapper = report_dir / 'report.tcl'
    script_dir = Path(__file__).parent
    wrapper.write_text('set env(DP_POWER_CONFIG) {' + str(config) + '}\nsource {' +
                       str(script_dir / 'export_functional_power.tcl') + '}\n')
    execute([machine['dc_shell'], '-f', str(wrapper)], report_dir, report_dir / 'dc.log', machine['setup_script'])
    if 'DP_FUNCTIONAL_REPORT_PASS' not in (report_dir / 'dc.log').read_text():
        raise ValueError('Supplemental power reporting failed')
    wrapper = report_dir / 'cones.tcl'
    wrapper.write_text('set env(DP_POWER_CONFIG) {' + str(config) + '}\nsource {' +
                       str(script_dir / 'export_functional_cones.tcl') + '}\n')
    execute([machine['dc_shell'], '-f', str(wrapper)], report_dir, report_dir / 'cones.log', machine['setup_script'])
    if 'FUNCTION_EXPORT_PASS' not in (report_dir / 'cones.log').read_text():
        raise ValueError('Supplemental function export failed')
    save(report_dir / 'manifest.json', dict(status='complete', no_compile=True,
        files_sha256={p.name: digest(p) for p in report_dir.iterdir() if p.is_file() and p.name != 'manifest.json'}))


def summarize(report_dirs, output):
    output.mkdir(parents=True, exist_ok=True)
    area_rows, power_rows, details, reconciliation, sources = [], [], [], [], []
    architecture_hashes = {}
    seen_points = set()
    for report in report_dirs:
        manifest = json.loads((report / 'manifest.json').read_text())
        for name, expected in manifest['files_sha256'].items():
            if digest(report / name) != expected:
                raise ValueError('Changed supplemental report: ' + name)
        source = json.loads((report / 'source.json').read_text())
        point, audit = check_point(ROOT / source['point'])
        if audit != source['audit']:
            raise ValueError('Original audit changed')
        top, mode = audit['top'], audit['format']
        if (top, mode) in seen_points:
            raise ValueError('Duplicate architecture/precision point: ' + top + '/' + mode)
        seen_points.add((top, mode))
        with (report / 'leaf_area.tsv').open() as stream:
            leaf_rows = list(csv.DictReader(stream, delimiter='\t'))
        leaves = {row['cell']: row for row in leaf_rows}
        if len(leaves) != len(leaf_rows):
            raise ValueError('Duplicate leaf area')
        netlist = ROOT / point['artifacts']['mapped_verilog']['path']
        assigned, cones = assign_cells(netlist, report / 'lib_functions.tsv', top, leaves)
        power = read_power(report / 'all_cell_net_power.rpt', leaves.keys())
        rounding = displayed_rounding_bounds(report / 'all_cell_net_power.rpt', leaves.keys())
        total_area = sum(row['area_um2'] for row in assigned.values())
        totals = {key: sum(row[key] for row in power.values()) for key in next(iter(power.values()))}
        checks = dict(area_um2=(total_area, audit['area_um2']))
        checks.update({key: (value, audit['static_mw' if key == 'leakage_mw' else key]) for key, value in totals.items()})
        for metric, (summed, official) in checks.items():
            relative = (summed - official) / max(abs(official), 1e-20)
            tolerance = 0.0005 if metric == 'area_um2' else rounding[metric] + max(1e-7, abs(official) * 0.00002)
            if not math.isfinite(summed) or abs(summed - official) > tolerance:
                raise ValueError(f'{top}/{mode}: {metric} leaf sum mismatch {relative}')
            reconciliation.append(dict(top=top, format=mode, metric=metric, leaf_sum=summed,
                                        official_total=official, difference_percent=100 * relative,
                                        allowed_absolute_difference=tolerance))
        sha = (digest(report / 'leaf_area.tsv'), digest(netlist))
        first = top not in architecture_hashes
        if not first and architecture_hashes[top] != sha:
            raise ValueError('Different netlists for precision points in ' + top)
        architecture_hashes[top] = sha
        for category in CATEGORIES:
            selected = [name for name, row in assigned.items() if row['category'] == category]
            area = sum(assigned[name]['area_um2'] for name in selected)
            if first:
                row = dict(top=top, category=category, total_um2=area, area_percent=100 * area / total_area,
                           cell_count=len(selected))
                for component in ('combinational', 'register', 'icg'):
                    row[component + '_um2'] = sum(assigned[n]['area_um2'] for n in selected if assigned[n]['component'] == component)
                area_rows.append(row)
            row = dict(top=top, format=mode, category=category)
            row.update({key: sum(power[n][key] for n in selected) for key in totals})
            for field in ('dynamic', 'leakage', 'total'):
                row[field + '_percent'] = 100 * row[field + '_mw'] / totals[field + '_mw']
            for component in ('combinational', 'register', 'icg'):
                row[component + '_dynamic_mw'] = sum(power[n]['dynamic_mw'] for n in selected if assigned[n]['component'] == component)
            power_rows.append(row)
        groups = defaultdict(lambda: dict(area_um2=0., dynamic_mw=0., leakage_mw=0., total_mw=0., cell_count=0))
        for name, row in assigned.items():
            entry = groups[row['category'], row['function'], row['component']]
            entry['area_um2'] += row['area_um2']
            entry['cell_count'] += 1
            for key in ('dynamic_mw', 'leakage_mw', 'total_mw'):
                entry[key] += power[name][key]
        details.extend(dict(top=top, format=mode, category=k[0], function=k[1], component=k[2], **v) for k, v in sorted(groups.items()))
        write_csv(report / 'cell_assignment.csv', [dict(cell=n, **row) for n, row in assigned.items()])
        save(report / 'cone_ownership.json', cones)
        sources.append(dict(top=top, format=mode, original_point=source['point'], report=str(report.relative_to(ROOT)),
                            dc_run=audit['dc_run'], export_id=audit['export_id'], leaf_count=len(leaves),
                            source_sha256=digest(report / 'source.json'), netlist_sha256=digest(netlist),
                            assignments_sha256=digest(report / 'cell_assignment.csv')))
    for name, rows in [('area', area_rows), ('power', power_rows), ('detail', details), ('reconciliation', reconciliation)]:
        write_csv(output / ('seven_functions_' + name + '.csv'), rows)
    save(output / 'seven_functions_sources.json', dict(status='PASS', categories=CATEGORIES, sources=sources,
        policy='Exclusive physical leaves, major module ownership plus register fields and direct-parent cones; cross-category shared logic in Others. No rescaling.',
        clock_policy='Register clock-pin energy included in cell internal power; ICG in Others. Net switching already included in driven-cell rows.',
        limitations=['Pre-layout, zero-delay SAIF; no CTS or SPEF.',
                    'Whole unpack modules include their local exponent decoding and INT magnitude conversion.',
                    'Legacy E64 C leading detection remains inside the whole C-unpack boundary.',
                    'Signed pair preparation belongs to SOP; group absolute value and shift delta to alignment.',
                    'S5 scaled-or-bypassed magnitude registers belong to multiplication in all modes.',
                    'These broad module boundaries differ from historical fine-grained SAT cone attribution.'],
        script_sha256=digest(Path(__file__))))
    print(f'{len(architecture_hashes)} architectures; {len(sources)} accepted power points; seven exclusive categories')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    cmd = commands.add_parser('export')
    cmd.add_argument('--point', type=Path, required=True)
    cmd.add_argument('--report', type=Path, required=True)
    cmd.add_argument('--machine', type=Path, default=ROOT / 'hw/power/configs/machine.local.json')
    cmd = commands.add_parser('summarize')
    cmd.add_argument('--reports', type=Path, nargs='+', required=True)
    cmd.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'export':
        export(args.point.resolve(), args.report.resolve(), args.machine.resolve())
    else:
        summarize([p.resolve() for p in args.reports], args.output.resolve())
