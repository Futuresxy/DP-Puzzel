#!/usr/bin/env python3
"""Freeze the six-netlist / three-format measurement plan; does not launch EDA.

This checks dataset and artifact identities only. An output plan is not an RTL
gate receipt, a gate-level simulation PASS, or permission to ignore stale gates.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASET = 'qwen3_8b_mlp_down_proj_1024'
CATALOG = ROOT / 'hw/dc_syn/records/latest_six_dp.json'
MODES = ('bf16', 'mxfp8_e4m3', 'mxfp4_e2m1')
CAPACITIES = {
    'dp_top': ('multi', (16, 32, 64)),
    'dp_top_t8h16q32e96': ('t8h16q32e96', (16, 32, 96)),
    'dp_top_t8h16q32e128': ('t8h16q32e128', (16, 32, 128)),
    'dp_top_t8h16q64e128_opt': ('t8h16q64e128_opt', (16, 64, 128)),
    'dp_top_e64': ('e', (None, None, 64)),
    'dp_top_q32e64': ('qe', (None, 32, 64)),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    catalog = json.loads(CATALOG.read_text())
    records = {record['top']: record for record in catalog['records']}
    if set(records) != set(CAPACITIES):
        raise ValueError('Unexpected architecture catalog')
    points = []
    window = None
    for top, (frontend, lengths) in CAPACITIES.items():
        record = records[top]
        artifacts = record['power_preparation']['artifacts']
        for item in artifacts.values():
            if digest(ROOT / item['path']) != item['sha256']:
                raise ValueError('Changed mapped artifact: ' + item['path'])
        for mode, logical_k in zip(MODES, lengths):
            if logical_k is None:
                continue
            directory = ROOT / 'test/data/power' / mode / f'K{logical_k}' / DATASET
            manifest = json.loads((directory / 'manifest.json').read_text())
            if (manifest['format'] != mode or manifest['logical_k'] != logical_k
                    or manifest['count'] != 1024 or frontend not in manifest['cmodel_vs_exact']):
                raise ValueError('Dataset does not match top capacity/model')
            for name, expected in manifest['files_sha256'].items():
                if digest(directory / name) != expected:
                    raise ValueError('Changed input/golden: ' + str(directory / name))
            if window is not None and window != manifest['recommended_measurement']:
                raise ValueError('Measurement windows differ')
            window = manifest['recommended_measurement']
            points.append(dict(top=top, cmodel_frontend=frontend, format=mode, logical_k=logical_k,
                               dc_run=record['run'], export_id=record['export_id'],
                               original_verification_id=record['verification_id'], artifacts=artifacts,
                               dataset_directory=str(directory.relative_to(ROOT)),
                               dataset_manifest_sha256=digest(directory / 'manifest.json'),
                               dataset_files_sha256=manifest['files_sha256'],
                               expected_field='cmodel_results.' + frontend,
                               status='planned_requires_rtl_gate_gls_saif_and_annotation_audits',
                               power_mw=None))
    return dict(schema_version=1, campaign='qwen3_8b_mlp_first3', status='plan_only',
                catalog_path=str(CATALOG.relative_to(ROOT)), catalog_sha256=digest(CATALOG),
                engine='VCS native gate-level SAIF + Synopsys Power Compiler',
                condition='original N12 TT 0.7V 85C / 1GHz / clock gating / L8 II1',
                measurement_window=window, pilot_top='dp_top', points=points,
                execution_order='dp_top three formats first; then remaining compatible points',
                saif_generated=False, power_measured=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'{len(result["points"])} planned points; no EDA executed; {args.output}')
