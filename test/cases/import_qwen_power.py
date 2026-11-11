#!/usr/bin/env python3
"""Import native Qwen3-8B MLP slices; preserve bits and regenerate two references.

Python >= 3.9. Reads only the explicitly selected upstream corpus. No simulator,
EDA tool, quantizer, RTL receipt or existing numerical dataset is modified.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

TEST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST))
from adapters.cmodel import ROOT, DEFAULT_CONFIG, evaluate, read_inputs, sha256, write_inputs
from adapters.logical import SCHEMA, packed_widths, write_logical_inputs
from cases.import_legacy import request_from_elements
from cases.import_petile_ratio import E_MODES, HEX_FILES, read_case, request_from_source
from reference.exact import DTYPES, reference, ulp_distance
from reference.logical import exact_logical, serialize_exact

CASE = 'batch1024_qwen3_8b_layer0_mlp_down_proj'
DATASET = 'qwen3_8b_mlp_down_proj_1024'
H_MODES = ('bf16', 'fp16')
Q_MODES = ('mxfp8_e4m3', 'mxfp8_e5m2')
MIXED = ('t8h16q32e96', 't8h16q32e128', 't8h16q64e128_opt')
WINDOW = dict(name='dp-qwen8b-middle512-v1', first_source_index=256,
              end_source_index_exclusive=768, cycles=512, frequency_hz=1_000_000_000,
              duration_ns=512, issue_policy='1024 independent transactions, once each, II=1',
              boundary='same clock phase before driving transactions 256 and 768',
              pipeline='includes steady-state in-flight transactions; not output-ID filtering')


def selections():
    return [('petile_full16', H_MODES, 16), ('petile_full16', Q_MODES, 32),
            ('petile_full16_low16', Q_MODES, 64), ('petile_full16', E_MODES, 64),
            ('petile_full16_fp48', E_MODES, 96), ('petile_full16_fp416', E_MODES, 128)]


def frontends(mode, logical_k):
    if mode in H_MODES:
        return ('multi',) + MIXED
    if mode in Q_MODES:
        return ('multi', MIXED[0], MIXED[1], 'qe') if logical_k == 32 else (MIXED[2],)
    return {64: ('multi', 'e', 'qe'), 96: (MIXED[0],), 128: (MIXED[1], MIXED[2])}[logical_k]


def read_high_precision(path, mode):
    metadata = json.loads((path / 'meta.json').read_text())
    source_type = 7 if mode == 'bf16' else 8
    expected = dict(format=mode, logical_k=16, dimk=16, dimk_words=16,
                    elements_per_word=1, active_word_count=16, group_size=4,
                    a_data_type=source_type, b_data_type=source_type, a_sf_type=2,
                    b_sf_type=2, c_type=0, out_type=0, rm=0,
                    group_layout=['full'] * 4, pegroup_layout=['full'] * 4,
                    golden_model='fp64_dequant_dot_plus_c_v1')
    if any(metadata[key] != value for key, value in expected.items()):
        raise ValueError('High-precision source contract mismatch')
    sizes = dict(a_data=16, b_data=16, a_scale=4, b_scale=4,
                 a_sf_group0=16, b_sf_group0=16, a_sf_group1=8, b_sf_group1=8,
                 c_data=1, golden_result_bits=1)
    widths = dict(a_data=16, b_data=16, a_scale=8, b_scale=8,
                  a_sf_group0=1, b_sf_group0=1, a_sf_group1=1, b_sf_group1=1,
                  c_data=32, golden_result_bits=32)
    values = {}
    for key in HEX_FILES:
        raw = [int(line, 16) for line in (path / (key + '.txt')).read_text().splitlines()]
        size = sizes[key]
        if len(raw) != 1024 * size or any(value < 0 or value >= 1 << widths[key] for value in raw):
            raise ValueError('High-precision source dimensions/range mismatch: ' + key)
        values[key] = [raw[index * size:(index + 1) * size] for index in range(1024)]
    values['golden_result_value'] = (path / 'golden_result_value.txt').read_text().splitlines()
    if len(values['golden_result_value']) != 1024:
        raise ValueError('Text golden count mismatch')
    for side in ('a', 'b'):
        if any(row != [127] * 4 for row in values[side + '_scale']):
            raise ValueError('High-precision source must use unit unused scale')
        if any(any(row) for field in ('sf_group0', 'sf_group1') for row in values[side + '_' + field]):
            raise ValueError('High-precision source has unexpected HiF4 metadata')
    return metadata, values


def audit_results(bits, exact_bits):
    distances = [ulp_distance(got, expected) for got, expected in zip(bits, exact_bits)]
    return dict(count=len(bits), bit_exact=sum(a == b for a, b in zip(bits, exact_bits)),
                max_ulp=max((value for value in distances if value is not None), default=0),
                nonfinite_mismatches=sum(value is None for value in distances),
                above_4=[dict(id=index, ulp=value) for index, value in enumerate(distances)
                         if value is not None and value > 4])


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))


def verify_source_files(source, batch_manifest):
    for relative, expected in batch_manifest['source_files'].items():
        if sha256(source.parent / relative) != expected:
            raise ValueError('Upstream sample provenance changed: ' + relative)


def import_power(source, destination):
    source = Path(source).resolve(strict=True)
    destination = Path(destination)
    batch_manifest = json.loads((source.parent / 'manifest.json').read_text())
    verify_source_files(source, batch_manifest)
    indexed = {entry['path']: entry for entry in batch_manifest['cases']}
    repository = Path(subprocess.check_output(
        ['git', '-C', str(source), 'rev-parse', '--show-toplevel'], text=True).strip())
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    model_sources = {str(path.relative_to(ROOT)): sha256(path)
                     for path in sorted((ROOT / 'src/cmodel').rglob('*'))
                     if path.is_file() and 'build' not in path.parts
                     and path.suffix in ('.cpp', '.hpp', '.txt')}
    reference_sources = {str(path.relative_to(ROOT)): sha256(path) for path in
                         [Path(__file__), TEST / 'cases/import_petile_ratio.py',
                          TEST / 'cases/import_legacy.py', TEST / 'adapters/cmodel.py',
                          TEST / 'adapters/logical.py', TEST / 'reference/exact.py',
                          TEST / 'reference/logical.py']}
    c_values = None
    datasets = []
    for ratio, modes, logical_k in selections():
        for mode in modes:
            path = source / ratio / mode / CASE
            source_entry = indexed[str(path.relative_to(source.parent))]
            for name, expected in source_entry['files'].items():
                if sha256(path / name) != expected:
                    raise ValueError('Upstream case checksum mismatch: ' + name)
            metadata, values = (read_high_precision(path, mode) if mode in H_MODES
                                else read_case(path, mode))
            if (metadata['txn_count'] != 1024 or metadata['logical_k'] != logical_k
                    or metadata['dataset_id'] != CASE or metadata['ratio_id'] != ratio):
                raise ValueError('Unexpected workload identity/count/native K')
            if metadata['distribution']['raw_sample_sha256'] != batch_manifest['source_files']['sources/down_proj_samples.pt']:
                raise ValueError('Source sample identity mismatch')
            if c_values is not None and c_values != values['c_data']:
                raise ValueError('Cross-format/K shared C mismatch')
            c_values = values['c_data']
            requests, references, scale_indices = [], [], []
            for index in range(1024):
                if mode in H_MODES:
                    request = request_from_elements(mode, values['a_data'][index],
                                                    values['b_data'][index], values['c_data'][index][0],
                                                    ident=index, last=index == 1023)
                    exact = reference(request, DEFAULT_CONFIG)
                else:
                    request, scale_indices = request_from_source(metadata, values, index, logical_k,
                                                                 ident=index, last=index == 1023)
                    exact = exact_logical(request, logical_k)
                requests.append(request)
                references.append(exact)
            exact_bits = [result['bits'] for result in references]
            source_audit = audit_results([row[0] for row in values['golden_result_bits']], exact_bits)
            if source_audit['nonfinite_mismatches'] or source_audit['max_ulp'] > 1:
                raise ValueError('Independent exact reference disagrees with source: ' + str(source_audit))
            results = {}
            with tempfile.TemporaryDirectory(prefix='dp-power-cmodel-') as scratch:
                for frontend in frontends(mode, logical_k):
                    results[frontend] = evaluate(requests, config={'frontend': frontend}, run_dir=scratch)
                    if any(row['id'] != request['id'] or row['last'] != request['last']
                           or row['d_datatype'] != 0 for row, request in zip(results[frontend], requests)):
                        raise ValueError('CModel response identity mismatch')
            primary = next(iter(results))
            cmodel_audit = {frontend: audit_results([int(row['d'], 16) for row in rows], exact_bits)
                            for frontend, rows in results.items()}
            expected_rows = [dict(id=index, d=results[primary][index]['d'], d_datatype=0,
                                  last=request['last'], cmodel_reference_frontend=primary,
                                  cmodel_results={frontend: rows[index]['d'] for frontend, rows in results.items()},
                                  exact_fp32_or_int32=f'{exact_bits[index]:08x}',
                                  exact_value=serialize_exact(references[index]))
                             for index, request in enumerate(requests)]
            source_rows = [dict(id=index, source_index=index,
                                source_fp64_fp32_bits=f"{values['golden_result_bits'][index][0]:08x}",
                                source_value_text=values['golden_result_value'][index]) for index in range(1024)]
            out = destination / mode / f'K{logical_k}' / DATASET
            out.parent.mkdir(parents=True, exist_ok=True)
            # Build beside the destination, then publish atomically; never replace a changed dataset.
            with tempfile.TemporaryDirectory(prefix='.qwen-import-', dir=out.parent) as temporary:
                staging = Path(temporary) / DATASET
                staging.mkdir()
                input_name = 'inputs.txt' if mode in H_MODES else 'inputs.jsonl'
                if mode in H_MODES:
                    write_inputs(staging / input_name, requests, 16)
                    if read_inputs(staging / input_name)[1] != [
                            dict(request, **{field: f'{int(request[field],16):0{width}x}'
                                             for field, width in dict(a=64,b=64,c=8,a_scale=8,b_scale=8,
                                                                      a_e1=4,b_e1=4,a_e2=2,b_e2=2).items()})
                            for request in requests]:
                        raise ValueError('Packed input round-trip failed')
                else:
                    write_logical_inputs(staging / input_name, requests, logical_k)
                write_rows(staging / 'expected.jsonl', expected_rows)
                write_rows(staging / 'source_reference.jsonl', source_rows)
                record = dict(schema='dp_inputs_v1' if mode in H_MODES else SCHEMA,
                              format=mode, datatype=DTYPES[mode], logical_k=logical_k,
                              count=1024, dataset=DATASET, purpose='workload_power', extraction='native',
                              selected_element_range=[0, logical_k], source_ratio=ratio,
                              source_repository=dict(name=repository.name, git_head=commit),
                              source_root=str(source.relative_to(repository)),
                              source_case=str(path.relative_to(repository)),
                              sources=source_entry['files'],
                              source_manifest_sha256=sha256(source.parent / 'manifest.json'),
                              source_sample_files=batch_manifest['source_files'],
                              distribution=metadata['distribution'], c_policy=metadata['c_policy'],
                              scale_policy=metadata['scale_policy'], source_scale_indices_per_group=scale_indices,
                              source_fp64_vs_exact=source_audit, cmodel_vs_exact=cmodel_audit,
                              cmodel_config=DEFAULT_CONFIG, cmodel_sources=model_sources,
                              cmodel_binary_sha256=sha256(ROOT / 'src/cmodel/build/dp_cmodel_cli'),
                              reference_sources=reference_sources,
                              mathematical_reference='Fraction exact dequantized dot+C, one FP32 RNE',
                              expected_semantics='d uses cmodel_reference_frontend; choose cmodel_results by hardware frontend',
                              rtl_status='not_run_on_this_workload', ppa_eligible=False,
                              recommended_measurement=WINDOW,
                              files_sha256={name: sha256(staging / name) for name in
                                            (input_name, 'expected.jsonl', 'source_reference.jsonl')})
                if mode in H_MODES:
                    record.update(k_fp16=16, input_sha256=sha256(staging / input_name))
                else:
                    record['packed_widths'] = packed_widths(DTYPES[mode], logical_k)
                write_json(staging / 'manifest.json', record)
                if any(file.stat().st_size > 5 * 1024 * 1024 for file in staging.iterdir()):
                    raise ValueError('Dataset file exceeds 5 MiB')
                if out.exists():
                    if ({file.name: sha256(file) for file in out.iterdir()} !=
                            {file.name: sha256(file) for file in staging.iterdir()}):
                        raise ValueError('Refusing to overwrite changed dataset: ' + str(out))
                else:
                    staging.rename(out)
            datasets.append(dict(path=str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
                                 format=mode, logical_k=logical_k, count=1024,
                                 source_fp64_vs_exact=source_audit, cmodel_vs_exact=cmodel_audit))
            print(f'{mode} K{logical_k}: 1024 rows, source/exact={source_audit["bit_exact"]}, '
                  f'CModel max ULP={ {key: value["max_ulp"] for key,value in cmodel_audit.items()} }', flush=True)
    return dict(schema_version=1, dataset=DATASET, datasets=datasets,
                total_unique_transactions=sum(item['count'] for item in datasets),
                total_cmodel_evaluations=sum(1024 * len(item['cmodel_vs_exact']) for item in datasets),
                recommended_measurement=WINDOW, saif_generated=False, power_measured=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True, help='Read-only petile_ratio root')
    parser.add_argument('--dest-root', type=Path, default=TEST / 'data/power')
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()
    summary = import_power(args.source_root, args.dest_root)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.summary, summary)
