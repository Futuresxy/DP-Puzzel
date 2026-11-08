#!/usr/bin/env python3
"""Partition dp_top area at real module boundaries without parent/child overlap.

Consumes an accepted DC hierarchical area report, not RTL operator estimates.
Local residuals retain their owner: registers, control AND inline arithmetic.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
LABELS = {
    'u_lane_unpack': 'Lane operand unpack (including S1 banks)',
    'u_mantissa_mul_bank': 'Lane mantissa multiplier bank',
    'u_exponent_add': 'Lane exponent add bank',
    'u_lane_exponent_max': 'Lane exponent MAX',
    'u_local_alignment': 'Lane alignment, E pair and sign processing',
    'u_lane_sop_tree': 'Lane SOP reduction tree',
    'lane_local': 'Lane local registers, control and inline logic',
    'u_scale_unpack_a': 'Group scale unpack A/B',
    'u_scale_unpack_b': 'Group scale unpack A/B',
    'u_scale_pair_mul': 'Group scale coefficient multiply',
    'u_group_scale_mul': 'Group magnitude scale multiply',
    'u_group_sop_add': 'Group SOP adder',
    'u_group_exponent_max': 'Group exponent MAX',
    'u_group_leading_detect': 'Group LZD',
    'group_local': 'Group local registers, control and inline logic',
    'u_global_alignment': 'Top global alignment (including MAX/sign/bypass)',
    'u_final_sop_tree': 'Top final SOP+C reduction tree',
    'u_fp32_output': 'Top abs/LZD/normalization/rounding/output select',
    'u_c_unpack': 'Top C unpack (including subnormal LZD)',
    'top_local': 'Top local registers, control and inline logic',
}


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def parse_report(path):
    rows = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) != 7:
            continue
        try:
            total, _, combinational, sequential, macro = map(float, fields[1:6])
        except ValueError:
            continue
        if fields[0] in rows or min(total, combinational, sequential, macro) < 0 or macro != 0:
            raise ValueError('Duplicate/invalid area row: ' + fields[0])
        rows[fields[0]] = dict(total=total, comb=combinational, seq=sequential, reference=fields[6])
    if 'dp_top' not in rows:
        raise ValueError('Expected dp_top report')
    children = defaultdict(list)
    for name in rows:
        if name == 'dp_top':
            continue
        parent = name.rsplit('/', 1)[0] if '/' in name else 'dp_top'
        if parent not in rows:
            raise ValueError('Missing parent: ' + parent)
        children[parent].append(name)
    errors = []
    for name, row in rows.items():
        difference = row['total'] - row['comb'] - row['seq'] - sum(rows[c]['total'] for c in children[name])
        # Each printed area has four decimal places; allow its rounding bound.
        if abs(difference) > (len(children[name]) + 3) * 0.000051:
            raise ValueError('Hierarchy does not reconcile: ' + name)
        errors.append(abs(difference))
    return rows, children, max(errors)


def summarize(run_id, output):
    run = ROOT / 'hw/dc_syn/runs' / run_id
    summary = json.loads((run/'summary.json').read_text())
    if summary['top'] != 'dp_top' or not summary['flow_pass']:
        raise ValueError('Requires a fully accepted dp_top synthesis')
    report = run/'reports/area_hierarchy.rpt'
    rows, children, max_error = parse_report(report)
    total = summary['area']['total_cell_area_um2']
    if abs(rows['dp_top']['total'] - total) > 0.000051:
        raise ValueError('Top area differs from accepted summary')
    groups = sorted(k for k in rows if re.fullmatch(r'g_group_\d+__u_group_unit', k))
    lanes = sorted(k for k in rows if re.fullmatch(r'g_group_\d+__u_group_unit/g_lane_\d+__u_lane', k))
    if len(groups) != 4 or len(lanes) != 8:
        raise ValueError('Expected T8H16Q32E64: four groups and eight lanes')
    cuts = []
    owners = [('dp_top', 'top', groups)]
    owners += [(g, 'group', [l for l in lanes if l.startswith(g+'/')]) for g in groups]
    owners += [(l, 'lane', []) for l in lanes]
    covered = set()
    for owner, level, expanded in owners:
        functional = [c for c in children[owner] if c not in expanded and '/clk_gate_' not in '/'+c]
        for name in functional:
            role = name.rsplit('/', 1)[-1]
            if role not in LABELS:
                raise ValueError('New function requires an explicit label: ' + name)
            cuts.append(dict(scope=LABELS[role], owner_level=level, instance=name,
                             area_um2=rows[name]['total'], source='inclusive subtree'))
            owned = {k for k in rows if k == name or k.startswith(name+'/')}
            if covered & owned:
                raise ValueError('Overlapping subtree')
            covered |= owned
        # Exact remainder includes owner-local cells and its ICG child wrappers.
        remainder = rows[owner]['total'] - sum(rows[c]['total'] for c in functional+expanded)
        cuts.append(dict(scope=LABELS[level+'_local'], owner_level=level, instance=owner,
                         area_um2=remainder, source='parent minus disjoint functional children'))
        owned = {owner} | {k for c in children[owner] if '/clk_gate_' in '/'+c
                          for k in rows if k == c or k.startswith(c+'/')}
        if covered & owned:
            raise ValueError('Overlapping local owner')
        covered |= owned
    if covered != rows.keys():
        raise ValueError('Hierarchy coverage incomplete')
    if abs(sum(r['area_um2'] for r in cuts) - total) > 0.000051:
        raise ValueError('Partition total mismatch')
    grouped = defaultdict(lambda: dict(instance_count=0, area_um2=0.0))
    for row in cuts:
        acc = grouped[(row['scope'], row['owner_level'])]
        acc['instance_count'] += 1
        acc['area_um2'] += row['area_um2']
        row['dp_percent'] = row['area_um2']/total*100
    modules = [dict(scope=k[0], owner_level=k[1], **v, dp_percent=v['area_um2']/total*100)
               for k,v in grouped.items()]
    modules.sort(key=lambda r: -r['area_um2'])
    lanes_area = sum(rows[l]['total'] for l in lanes)
    groups_area = sum(rows[g]['total'] for g in groups)
    levels = [dict(scope='Eight lanes', area_um2=lanes_area, dp_percent=100*lanes_area/total),
              dict(scope='Four groups excluding lanes', area_um2=groups_area-lanes_area, dp_percent=100*(groups_area-lanes_area)/total),
              dict(scope='Top excluding groups', area_um2=total-groups_area, dp_percent=100*(total-groups_area)/total)]
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output/'fixed_unpack_module_area.csv', modules)
    write_csv(output/'fixed_unpack_module_area_instances.csv', cuts)
    write_csv(output/'fixed_unpack_module_area_levels.csv', levels)
    source = dict(run_id=run_id, export_id=summary['export_id'], total_um2=total,
                  report=str(report.relative_to(ROOT)), report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                  hierarchy_rows=len(rows), covered_rows=len(covered), max_parent_reconciliation_error_um2=max_error,
                  rounded_partition_sum_um2=sum(r['area_um2'] for r in cuts),
                  local_combinational_sum_um2=sum(r['comb'] for r in rows.values()),
                  local_sequential_sum_um2=sum(r['seq'] for r in rows.values()),
                  official_combinational_um2=summary['area']['combinational_area_um2'],
                  official_sequential_um2=summary['area']['sequential_area_um2'],
                  policy='Real module boundaries. Registers follow physical owner. ICGs in owner-local remainder. No overlap; not the seven functional categories.',
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output/'fixed_unpack_module_area_sources.json').write_text(json.dumps(source,indent=2)+'\n')
    print(json.dumps(dict(levels=levels,modules=modules,audit=source),indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'paper/data/H16Q32E64_area')
    args = parser.parse_args()
    summarize(args.run_id, args.output)
