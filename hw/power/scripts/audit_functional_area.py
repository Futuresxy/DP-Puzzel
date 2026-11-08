#!/usr/bin/env python3
"""Cross-check mapped hierarchy totals and drill into three coarse area categories.

No EDA run or RTL changes. Parent-local logic is deliberately kept mixed when
synthesis does not preserve a separate arithmetic hierarchy.
"""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path

from summarize_functional_power import ALIGN, ADD, EXP, ROOT, classify, digest, write_csv


def subdivision(name, category, component):
    if component == 'register':
        return 'Assigned pipeline registers'
    if category == ALIGN:
        if '__u_local_align_shift/' in name:
            return '32 local RTZ shift cores'
        if '__u_global_align_shift/' in name:
            return '5 global bidirectional shift cores'
        if any(token in name for token in ('/u_lane_exponent_max/', '/u_group_exponent_max/',
                                           '/u_global_anchor_max/')):
            return 'Lane group and global MAX trees'
        if '/u_local_alignment/' in name:
            return 'Local mixed logic: pair sign placement delta selection'
        if name.startswith('u_global_alignment/'):
            return 'Global mixed logic: anchor delta sign selection'
    if category == EXP:
        if '__u_wide_add/' in name:
            return '16 wide exponent add cores (8-bit inputs)'
        if '__u_narrow_add/' in name:
            return '16 narrow exponent add cores (5-bit inputs)'
        if '/u_exponent_add/' in name:
            return 'Exponent bank input and output routing'
    if category == ADD:
        if '/u_lane_sop_tree/' in name:
            return '8 lane reduction trees: 4 operands each'
        if '/u_group_sop_add/' in name:
            return '4 group adders: 2 operands each'
        if name.startswith('u_final_sop_tree/'):
            return '1 final reduction tree: 5 operands'
    raise ValueError('Unexpected focused-category leaf: ' + name)


def audit(data_dir):
    source = json.loads((data_dir / 'current_dp_top_sources.json').read_text())
    point = source['sources'][0]
    leaf_path = ROOT / point['supplemental_point'] / 'leaf_area.tsv'
    if digest(leaf_path) != point['reports_sha256']['leaf_area.tsv']:
        raise ValueError('Leaf area input changed')
    hierarchy_path = ROOT / source['dc_run'] / 'reports/area_hierarchy.rpt'
    # Independently sum every ancestor, then compare to DC inclusive hierarchy
    # reports. Ancestor totals are validation only, never added to the pie.
    ancestors = defaultdict(float)
    groups = defaultdict(lambda: dict(cell_count=0, total_um2=0.0))
    total = 0.0
    seen = set()
    for row in csv.DictReader(leaf_path.open(), delimiter='\t'):
        name, area = row['cell'], float(row['area_um2'])
        if name in seen:
            raise ValueError('Duplicate leaf')
        seen.add(name)
        total += area
        parts = name.split('/')
        for index in range(1, len(parts)):
            ancestors['/'.join(parts[:index])] += area
        category, _, component = classify(name, row['sequential'] == 'true')
        if category in (ALIGN, ADD, EXP):
            key = category, subdivision(name, category, component), component
            groups[key]['cell_count'] += 1
            groups[key]['total_um2'] += area
    ancestors['dp_top'] = total
    comparisons = []
    for line in hierarchy_path.read_text().splitlines():
        fields = line.split()
        if not fields or fields[0] not in ancestors:
            continue
        reference = float(fields[1])
        delta = ancestors[fields[0]] - reference
        if abs(delta) > 0.0005:
            raise ValueError(f'Hierarchy mismatch: {fields[0]} {delta}')
        comparisons.append(dict(hierarchy=fields[0], leaf_sum_um2=ancestors[fields[0]],
                                dc_hierarchy_um2=reference, difference_um2=delta))
    if {r['hierarchy'] for r in comparisons} != ancestors.keys():
        raise ValueError('DC hierarchy inventory incomplete')
    category_totals = defaultdict(float)
    for (category, _, _), values in groups.items():
        category_totals[category] += values['total_um2']
    baseline = {row['category']: float(row['total_um2'])
                for row in csv.DictReader((data_dir / 'current_dp_top_area.csv').open())}
    for category, area in category_totals.items():
        if abs(area - baseline[category]) > 1e-7:
            raise ValueError('Drilldown does not reconstruct original category: ' + category)
    rows = [dict(category=key[0], subfunction=key[1], component=key[2], **values,
                 total_design_percent=values['total_um2'] / total * 100,
                 within_category_percent=values['total_um2'] / category_totals[key[0]] * 100)
            for key, values in sorted(groups.items())]
    write_csv(data_dir / 'current_dp_top_area_audit.csv', rows)
    run = ROOT / source['report_run']
    write_csv(run / 'area_hierarchy_crosscheck.csv', comparisons)
    manifest = dict(status='PASS', method='All ancestor inclusive totals independently cross-checked against original DC report',
                    leaf_count=len(seen), hierarchy_count=len(comparisons),
                    max_abs_hierarchy_difference_um2=max(abs(r['difference_um2']) for r in comparisons),
                    hierarchy_tolerance_um2=0.0005,
                    source_report=str(hierarchy_path.relative_to(ROOT)), source_report_sha256=digest(hierarchy_path),
                    leaf_input=str(leaf_path.relative_to(ROOT)), leaf_input_sha256=digest(leaf_path),
                    script_sha256=digest(Path(__file__)),
                    scope='Hierarchical area accounting correct; mixed parent-local arithmetic is not separately attributed')
    (data_dir / 'current_dp_top_area_audit.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'paper/data/H16Q32E64_area')
    audit(parser.parse_args().data_dir)
