#!/usr/bin/env python3
"""Freeze a model and derive real-workload goldens for one explicit DP profile.

The source dataset is immutable. Exact mathematical and original source results
remain alongside the new CModel results. Plan creation requires a passing archived
DC result; it does not replace RTL/GLS/SAIF verification.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'test')]
from adapters.cmodel import DEFAULT_CONFIG, evaluate, read_inputs, sha256
from adapters.logical import read_logical_inputs
from cases.import_qwen_power import audit_results, WINDOW
from dp_power_gate import frozen_dc_source


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def local_path(path):
    return str(Path(path).resolve().relative_to(ROOT.resolve()))


def freeze_reference(source_root, destination):
    source_root = Path(source_root).resolve()
    destination = Path(destination).resolve()
    local_path(destination)
    sources = {str(path.relative_to(source_root)): sha256(path)
               for path in sorted((source_root / 'src/cmodel').rglob('*'))
               if path.is_file() and 'build' not in path.parts
               and path.suffix in ('.cpp', '.hpp', '.txt')}
    binary = source_root / 'src/cmodel/build/dp_cmodel_cli'
    identity = dict(sources=sources, binary_sha256=sha256(binary))
    if destination.exists():
        recorded = json.loads((destination / 'reference.json').read_text())
        if recorded != identity:
            raise ValueError('Refusing to overwrite a different reference model')
        if sha256(destination / 'dp_cmodel_cli') != identity['binary_sha256']:
            raise ValueError('Archived reference binary changed')
        for name, expected in sources.items():
            if sha256(destination / 'sources' / name) != expected:
                raise ValueError('Archived reference source changed: ' + name)
        return identity
    destination.mkdir(parents=True)
    for name in sources:
        target = destination / 'sources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / name, target)
    shutil.copy2(binary, destination / 'dp_cmodel_cli')
    save(destination / 'reference.json', identity)
    return identity


def derive(source, destination, frontend, archive, identity):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    original = json.loads((source / 'manifest.json').read_text())
    capacities = {'t8h16q64e64': (64, 64), 't8h16q32e192': (32, 192),
                  't8h16q32e256': (32, 256), 't8h16q96e192': (96, 192),
                  't8h16q128e256': (128, 256)}
    if frontend not in capacities:
        raise ValueError('Unsupported expansion profile: ' + frontend)
    q_k, e_k = capacities[frontend]
    datatype = original['datatype']
    native_k = 16 if datatype in (1, 2) else q_k if 3 <= datatype <= 6 else e_k if 7 <= datatype <= 9 else None
    if native_k is None or original['logical_k'] != native_k:
        raise ValueError('Workload is not the native K of this profile/mode')
    for name, expected in original['files_sha256'].items():
        if sha256(source / name) != expected:
            raise ValueError('Source dataset changed: ' + name)
    input_name = 'inputs.txt' if (source / 'inputs.txt').exists() else 'inputs.jsonl'
    requests = (read_inputs(source / input_name)[1] if input_name == 'inputs.txt'
                else read_logical_inputs(source)[1])
    expected = [json.loads(line) for line in (source / 'expected.jsonl').read_text().splitlines()]
    if len(requests) != 1024 or len(expected) != 1024:
        raise ValueError('Power requires the original 1024 transactions')
    config = dict(DEFAULT_CONFIG, architecture_v19=True)
    with tempfile.TemporaryDirectory(prefix='dp-expanded-reference-') as temporary:
        results = evaluate(requests, config=dict(config, frontend=frontend),
                           binary=archive / 'dp_cmodel_cli', run_dir=temporary)
    exact = [int(row['exact_fp32_or_int32'], 16) for row in expected]
    audit = audit_results([int(row['d'], 16) for row in results], exact)
    if audit['nonfinite_mismatches'] or audit['above_4']:
        raise ValueError('Reference exceeds the existing exact-math bound: ' + str(audit))
    rows = []
    for request, result, old in zip(requests, results, expected):
        if (result['id'] != request['id'] or result['last'] != request['last']
                or result['d_datatype'] != 0 or old['id'] != request['id']):
            raise ValueError('Reference identity/type mismatch')
        row = dict(old, d=result['d'], d_datatype=0, last=request['last'],
                   cmodel_reference_frontend=frontend,
                   cmodel_results={frontend: result['d']})
        if 'cmodel_status' in row:
            row['cmodel_status'] = 'evaluated'
        if 'cmodel_result' in row:
            row['cmodel_result'] = result['d']
        rows.append(row)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.derive-', dir=destination.parent) as temporary:
        staging = Path(temporary) / 'data'
        staging.mkdir()
        for name in (input_name, 'source_reference.jsonl'):
            shutil.copy2(source / name, staging / name)
        (staging / 'expected.jsonl').write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n'
                                                      for row in rows))
        manifest = dict(original, cmodel_config=config, cmodel_sources=identity['sources'],
                        cmodel_binary_sha256=identity['binary_sha256'],
                        cmodel_vs_exact={frontend: audit},
                        derived_from=dict(directory=local_path(source),
                                          manifest_sha256=sha256(source / 'manifest.json')),
                        recommended_measurement=WINDOW, rtl_status='not_run_on_this_workload',
                        ppa_eligible=False,
                        files_sha256={name: sha256(staging / name) for name in
                                      (input_name, 'expected.jsonl', 'source_reference.jsonl')})
        if 'cmodel_status' in manifest:
            manifest['cmodel_status'] = 'evaluated'
        save(staging / 'manifest.json', manifest)
        if destination.exists():
            if {p.name: sha256(p) for p in destination.iterdir()} != {p.name: sha256(p) for p in staging.iterdir()}:
                raise ValueError('Refusing to overwrite changed derived dataset')
        else:
            staging.rename(destination)
    return manifest


def make_plan(frontend, archive, datasets, dc_run, campaign):
    resolved = json.loads((dc_run / 'inputs/resolved.json').read_text())
    gate = resolved['gate']
    if gate['top'] != 'dp_top_' + frontend:
        raise ValueError('DC top does not match profile')
    if (resolved['technology']['pvt'] != dict(corner='TT', voltage_v=0.7, temperature_c=85)
            or resolved['constraints']['period_ns'] != 1
            or resolved['constraints']['clock_gating'] is not True):
        raise ValueError('DC result does not use the declared N12 TT 1GHz gated condition')
    if resolved['technology']['technology_id'] != 'n12-bwp6t-120a-base-lvt-tt-0p7v-85c':
        raise ValueError('Unexpected technology profile')
    artifacts = {}
    for role, suffix in [('mapped_verilog', '_mapped.v'), ('ddc', '.ddc'), ('sdc', '.sdc')]:
        path = dc_run / 'netlist' / (gate['top'] + suffix)
        artifacts[role] = dict(path=local_path(path), sha256=sha256(path), bytes=path.stat().st_size)
    points = []
    for directory in datasets:
        manifest = json.loads((directory / 'manifest.json').read_text())
        if set(manifest['cmodel_vs_exact']) != {frontend}:
            raise ValueError('Derived dataset/frontend mismatch')
        point = dict(top=gate['top'], cmodel_frontend=frontend,
                     cmodel_config=manifest['cmodel_config'], format=manifest['format'],
                     logical_k=manifest['logical_k'], dc_run=local_path(dc_run),
                     export_id=gate['export_id'], original_verification_id=gate['verification_id'],
                     artifacts=artifacts, dataset_directory=local_path(directory),
                     dataset_manifest_sha256=sha256(directory / 'manifest.json'),
                     dataset_files_sha256=manifest['files_sha256'],
                     reference_model=dict(directory=local_path(archive),
                                          manifest_sha256=sha256(archive / 'reference.json')),
                     expected_field='cmodel_results.' + frontend,
                     status='planned_requires_rtl_gate_gls_saif_and_annotation_audits', power_mw=None)
        frozen_dc_source(ROOT, point)
        points.append(point)
    return dict(schema_version=1, campaign=campaign, status='new_dc_bound_ready_for_replay',
                engine='VCS native gate-level SAIF + Synopsys Power Compiler',
                condition='N12 TT 0.7V 85C / 1GHz / clock gating / L8 II1',
                measurement_window=WINDOW, saif_generated=False, power_measured=False, points=points)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', required=True)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, action='append', required=True)
    parser.add_argument('--dc-run', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if bool(args.dc_run) != bool(args.output):
        parser.error('--dc-run and --output must be supplied together')
    archive = args.reference.resolve()
    identity = freeze_reference(args.source_root, archive)
    datasets = []
    for source in args.dataset:
        metadata = json.loads((source / 'manifest.json').read_text())
        target = archive / 'data' / args.frontend / metadata['format']
        manifest = derive(source, target, args.frontend, archive, identity)
        datasets.append(target)
        print(json.dumps(dict(dataset=local_path(target), audit=manifest['cmodel_vs_exact'])))
    if args.output:
        plan = make_plan(args.frontend, archive, datasets, args.dc_run.resolve(), args.output.stem)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        save(args.output, plan)


if __name__ == '__main__':
    main()
