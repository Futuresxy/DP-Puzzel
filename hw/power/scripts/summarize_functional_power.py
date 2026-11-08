#!/usr/bin/env python3
"""Attribute the accepted dp_top leaf cells once, then aggregate area and SAIF power.

This is an implementation-specific accounting policy, not automatic recognition
of arbitrary RTL arithmetic. Ambiguous inline/shared cells remain in Others.
Raw instance/reference tables stay in the ignored reporting run.
"""
import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

CATEGORIES = (
    'Data unpacking', 'Mantissa & scale multiplication', 'Exponent arithmetic',
    'Alignment & exponent selection', 'Addition & accumulation',
    'LZD, normalization & rounding', 'Others',
)
UNPACK, MUL, EXP, ALIGN, ADD, NORM, OTHER = CATEGORIES
MODES = ('bf16', 'mxfp8_e4m3', 'mxfp4_e2m1')
ROOT = Path(__file__).resolve().parents[3]
POWER_ROW = re.compile(
    r'^(\S+)\s+([\d.e+\-]+)\s+([\d.e+\-]+)\s+([\d.e+\-]+)\s+\([^)]*\)\s+([\d.e+\-]+)')


def classify(name, sequential):
    """Return one exclusive (category, subfunction, physical component)."""
    component = 'register' if sequential else 'combinational'
    if '/clk_gate_' in '/' + name:
        return OTHER, 'Clock gating cells', 'icg'
    module_rules = (
        ('/u_subnormal_detect/', NORM, 'C subnormal leading detection'),
        ('/u_lane_unpack/', UNPACK, 'Operand unpack and S1 banks'),
        ('/u_scale_unpack_a/', UNPACK, 'Scale unpack'),
        ('/u_scale_unpack_b/', UNPACK, 'Scale unpack'),
        ('/u_c_unpack/', UNPACK, 'C unpack'),
        ('/u_mantissa_mul_bank/', MUL, 'Element multiplier bank'),
        ('/u_scale_pair_mul/', MUL, 'Scale coefficient multiplier'),
        ('/u_group_scale_mul/', MUL, 'Group magnitude scale multiplier'),
        ('/u_exponent_add/', EXP, 'Element exponent addition'),
        ('/u_lane_exponent_max/', ALIGN, 'Lane exponent MAX'),
        ('/u_group_exponent_max/', ALIGN, 'Group exponent MAX'),
        ('/u_local_alignment/', ALIGN, 'Local alignment including pair preprocessing'),
        ('/u_global_alignment/', ALIGN, 'Global alignment MAX delta and sign restore'),
        ('/u_lane_sop_tree/', ADD, 'Lane reduction tree'),
        ('/u_group_sop_add/', ADD, 'Group reduction adder'),
        ('/u_final_sop_tree/', ADD, 'Final reduction tree'),
        ('/u_group_leading_detect/', NORM, 'Group leading detection'),
        ('/u_fp32_output/', NORM, 'Final normalization rounding and encoding'),
    )
    for token, category, function in module_rules:
        if token in '/' + name:
            return category, function, component
    if sequential:
        match = re.search(r'ff_s\d_s\d_(.*?)_ff_storage_out_q_reg', name)
        field = match.group(1) if match else ''
        if field in ('product_low', 'product_upper', 'active', 'negative'):
            return MUL, 'S2 products and product sidebands', component
        if field.startswith('coeff_q_'):
            return MUL, 'Scale coefficient pipeline', component
        if field == 'out_magnitude':
            return MUL, 'S5 scaled or bypassed magnitude register', component
        if field in ('exponents', 'hif4_exponent'):
            return EXP, 'S2 element exponent registers', component
        if field.startswith('scale_exp_q_') or (field == 'out_anchor' and '/g_lane_' not in name):
            return EXP, 'Group scale exponent and S5 anchor registers', component
        if field in ('ea', 'eb', 'sa', 'sb', 'nan_s1'):
            return UNPACK, 'S1 scale decode registers', component
        if field in ('anchor_s2', 'anchor_s3', 'out_anchor'):
            return ALIGN, 'Lane anchor pipeline', component
        if field in ('leaf_lower', 'leaf_upper'):
            return ALIGN, 'S3 aligned leaf registers', component
        if field in ('leaves', 'common_s6', 'common_s7'):
            return ALIGN, 'Global aligned operands and common exponent registers', component
        if field in ('out_sop', 'out_negative', 'sum'):
            return ADD, 'Lane group and final sum registers', component
        if field in ('out_z', 'c_z', 'out_d'):
            return NORM, 'Leading count and final output registers', component
        if field in ('c_magnitude', 'c_negative', 'c_anchor', 'c_special'):
            return UNPACK, 'S5 C decode registers', component
        if field == 'c_raw':
            return OTHER, 'Raw C transport registers', component
        if field and any(x in field for x in ('valid', 'type', 'last', 'special', 'negative', 'nan')):
            return OTHER, 'Control and special-value registers', component
        return OTHER, 'Unattributed registers', component
    return OTHER, 'Inline shared control and unattributed combinational logic', component


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def read_power(path, names):
    text = path.read_text()
    if 'Dynamic Power Units = 1mW' not in text or 'Leakage Power Units = 1nW' not in text:
        raise ValueError('Unexpected report power units')
    result = {}
    for line in text.splitlines():
        match = POWER_ROW.match(line)
        if not match or match[1] not in names:
            continue  # Exclude hierarchy subtotals and net rows.
        name = match[1]
        if name in result:
            raise ValueError('Duplicate leaf power: ' + name)
        internal, switching, leakage = (float(match[i]) for i in (2, 3, 5))
        values = dict(internal_mw=internal, switching_mw=switching,
                      dynamic_mw=internal + switching, leakage_mw=leakage * 1e-6)
        values['total_mw'] = values['dynamic_mw'] + values['leakage_mw']
        # Library characterization can produce tiny negative internal energy.
        # Preserve it instead of clamping and biasing the category totals.
        if any(not math.isfinite(x) for x in values.values()) or switching < 0 or leakage < 0:
            raise ValueError('Invalid power: ' + name)
        result[name] = values
    if result.keys() != names:
        raise ValueError('Missing/extra leaf power rows: ' + str(len(names - result.keys())))
    return result


def summarize(run, output):
    output.mkdir(parents=True, exist_ok=True)
    area_path = run / MODES[0] / 'leaf_area.tsv'
    leaves = {}
    for row in csv.DictReader(area_path.open(), delimiter='\t'):
        name = row['cell']
        if name in leaves:
            raise ValueError('Duplicate leaf area: ' + name)
        area = float(row['area_um2'])
        if not math.isfinite(area) or area < 0:
            raise ValueError('Invalid area')
        leaves[name] = (classify(name, row['sequential'] == 'true'), area)
    area_total = sum(x[1] for x in leaves.values())
    grouped = defaultdict(lambda: dict(cell_count=0, total_um2=0.0))
    for key, area in leaves.values():
        grouped[key]['cell_count'] += 1
        grouped[key]['total_um2'] += area
    detail = []
    for (category, function, component), values in sorted(grouped.items()):
        detail.append(dict(category=category, function=function, component=component,
                           **values, area_percent=100 * values['total_um2'] / area_total))
    area_rows = []
    for category in CATEGORIES:
        entries = [r for r in detail if r['category'] == category]
        row = dict(category=category)
        for component in ('combinational', 'register', 'icg'):
            row[component + '_um2'] = sum(r['total_um2'] for r in entries if r['component'] == component)
        row['cell_count'] = sum(r['cell_count'] for r in entries)
        row['total_um2'] = sum(r['total_um2'] for r in entries)
        row['area_percent'] = row['total_um2'] / area_total * 100
        area_rows.append(row)
    write_csv(output / 'current_dp_top_area.csv', area_rows)
    write_csv(output / 'current_dp_top_area_detail.csv', detail)
    # Auditable per-instance assignment stays local (contains library-level details).
    write_csv(run / 'cell_assignment.csv', [dict(cell=n, category=k[0], function=k[1],
              component=k[2], area_um2=a) for n, (k, a) in leaves.items()])
    power_rows, power_detail, reconciliation, sources = [], [], [], []
    for mode in MODES:
        point = run / mode
        if digest(point / 'leaf_area.tsv') != digest(area_path):
            raise ValueError('Modes do not use identical mapped cells')
        if 'DP_FUNCTIONAL_REPORT_PASS' not in (point / 'dc.log').read_text():
            raise ValueError('Incomplete reporting run')
        original = json.loads((point / 'source.json').read_text())
        audit = original['audit']
        if audit['status'] != 'PASS' or audit['dc_run'] != 'hw/dc_syn/runs/dc_dp_top_11081432':
            raise ValueError('Unexpected acceptance source')
        # Reject stale/tampered evidence, including the original RTL/GLS results.
        for filename, expected in audit['artifacts_sha256'].items():
            if digest(ROOT / filename) != expected:
                raise ValueError('Original artifact changed: ' + filename)
        power = read_power(point / 'all_cell_net_power.rpt', leaves.keys())
        grouped_power = defaultdict(lambda: defaultdict(float))
        for name, values in power.items():
            for field, value in values.items():
                grouped_power[leaves[name][0]][field] += value
        totals = {field: sum(v[field] for v in power.values()) for field in next(iter(power.values()))}
        for key, values in sorted(grouped_power.items()):
            power_detail.append(dict(format=mode, category=key[0], function=key[1],
                                     component=key[2], **values))
        for category in CATEGORIES:
            entries = [(key, value) for key, value in grouped_power.items() if key[0] == category]
            row = dict(format=mode, category=category)
            for field in totals:
                row[field] = sum(value[field] for _, value in entries)
            for component in ('combinational', 'register', 'icg'):
                row[component + '_dynamic_mw'] = sum(v['dynamic_mw'] for k, v in entries if k[2] == component)
            for field in ('dynamic', 'leakage', 'total'):
                row[field + '_percent'] = row[field + '_mw'] / totals[field + '_mw'] * 100
            power_rows.append(row)
        comparisons = dict(area_um2=(area_total, audit['area_um2']))
        for field in ('internal_mw', 'switching_mw', 'dynamic_mw', 'leakage_mw', 'total_mw'):
            comparisons[field] = (totals[field], audit['static_mw' if field == 'leakage_mw' else field])
        for field, (summed, reference) in comparisons.items():
            difference = summed - reference
            percent = 100 * difference / reference
            # Cell report values have limited precision; never rescale categories.
            if abs(percent) > 0.02:
                raise ValueError(f'{mode}: {field} does not reconcile: {percent}%')
            reconciliation.append(dict(format=mode, metric=field, leaf_sum=summed,
                                       accepted_total=reference, difference=difference,
                                       difference_percent=percent))
        sources.append(dict(format=mode, original_point=original['point'],
                            original_audit_sha256=digest(ROOT / original['point'] / 'power_audit.json'),
                            supplemental_point=str(point.relative_to(ROOT)),
                            reports_sha256={name: digest(point / name) for name in
                                ('leaf_area.tsv', 'all_cell_net_power.rpt', 'power.rpt', 'activity_missing.rpt')}))
    write_csv(output / 'current_dp_top_power.csv', power_rows)
    write_csv(output / 'current_dp_top_power_detail.csv', power_detail)
    write_csv(output / 'current_dp_top_reconciliation.csv', reconciliation)
    manifest = dict(schema_version=1, top='dp_top', capacity='T8H16Q32E64',
        export_id='DP_verilog_a32ed7ef4b093ffa', dc_run='hw/dc_syn/runs/dc_dp_top_11081432',
        report_run=str(run.relative_to(ROOT)), technology=audit['technology'],
        frozen_input_gate_sha256=digest(run / 'frozen_input_gate.json'),
        parameters=dict(K_FP16=16, LOCAL_W=28, GLOBAL_W=40, latency=8, ii=1),
        frequency_hz=audit['frequency_hz'], duration_ns=audit['duration_ns'],
        activity='VCS native gate-level SAIF; Qwen3-8B MLP; zero delay, pre-CTS, no SPEF',
        attribution='exclusive leaf instances; functional hierarchy plus explicit register field rules',
        normalization='Shares use leaf sums. Accepted totals and unadjusted rounding residuals are separate.',
        clock_accounting='Register clock-pin internal power belongs to registers; ICG plus driven nets in Others.',
        switching_accounting='Each cell includes its driven-net switching; net rows are not added again.',
        limitations=['Local alignment includes E pair preprocessing, routing and sign restore, not just shifters.',
                    'Inline group exponent/abs/mux and shared control not unambiguously attributed remain in Others.',
                    'S5 scaled-or-bypassed magnitude registers belong to multiplication, including bypass modes.',
                    'Output normalization category includes integer/output conversion logic.',
                    'Library and cell-report rounding remains visible; no proportional residual allocation.'],
        leaf_count=len(leaves), register_count=sum(k[2]=='register' for k,_ in leaves.values()),
        icg_count=sum(k[2]=='icg' for k,_ in leaves.values()),
        sources=sources,
        scripts_sha256={str(Path(__file__).relative_to(ROOT)):digest(Path(__file__)),
                        'hw/power/scripts/export_functional_power.tcl':digest(Path(__file__).with_name('export_functional_power.tcl'))})
    (output / 'current_dp_top_sources.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'{len(leaves)} exclusive leaves; area {area_total:.6f} um2; {len(power_rows)} power summary rows')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'paper/data/H16Q32E64_area')
    args = parser.parse_args()
    summarize(args.run.resolve(), args.output.resolve())
