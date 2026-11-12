#!/usr/bin/env python3
"""Copy native low32/low48 Q/E corpora and normalize exact mathematical references.

Never modifies upstream files, truncates K, or claims RTL/PPA acceptance. Raw
copies plus source manifest/sample dependencies allow replay without the sibling
checkout. Python 3.11; run from any directory with an explicit --source-repo.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'test'))
from adapters.cmodel import sha256
from adapters.logical import SCHEMA, packed_widths, read_logical_inputs, write_logical_inputs
from cases.import_petile_ratio import (E_MODES, Q_MODES, HEX_FILES, SEGMENTS,
                                      SOURCE_TYPES, SOURCE_SCALE_TYPES, request_from_source)
from cases.import_qwen_power import CASE, WINDOW, audit_results
from reference.exact import DTYPES, FORMATS
from reference.logical import exact_logical, serialize_exact

RELATIVE = Path('HW/tests/data/petile_test_data')
BATCH = 'PETileRatio_Qwen8BMLPPower_1027202452'
RATIOS = ('petile_full16_low32', 'petile_full16_low48')
RAW = ROOT / 'hw/power/workloads/raw/petile_extended'
DEST = ROOT / 'hw/power/workloads/petile_extended'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def copy_verified(source, target, expected=None):
    fingerprint = sha256(source)
    if expected is not None and fingerprint != expected:
        raise ValueError('Source hash mismatch: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != fingerprint:
            raise ValueError('Refusing to replace changed raw input: ' + str(target))
    else:
        shutil.copy2(source, target)
    if sha256(target) != fingerprint:
        raise ValueError('Copy checksum failed: ' + str(target))
    return dict(sha256=fingerprint, bytes=target.stat().st_size)


def read_native(path, mode, ratio):
    """Strict low-only extension layout, preserving each physical source word."""
    metadata = json.loads((path / 'meta.json').read_text())
    words = 48 if ratio == RATIOS[0] else 64
    elements = 4 if mode in E_MODES else 2
    layout = ['full'] * 4 + ['low'] * (words // 4 - 4)
    wanted = dict(format=mode, ratio_id=ratio, dimk_words=words, dimk=words,
                  active_word_count=words, elements_per_word=elements,
                  logical_k=words * elements, group_size=4,
                  group_layout=layout, pegroup_layout=layout,
                  a_data_type=SOURCE_TYPES[mode], b_data_type=SOURCE_TYPES[mode],
                  a_sf_type=SOURCE_SCALE_TYPES.get(mode, 2),
                  b_sf_type=SOURCE_SCALE_TYPES.get(mode, 2), c_type=0, out_type=0, rm=0,
                  golden_model='fp64_dequant_dot_plus_c_v1')
    if any(metadata.get(key) != value for key, value in wanted.items()):
        raise ValueError('Unsupported native metadata: ' + str(path))
    count = metadata['txn_count']
    sizes = dict(a_data=words, b_data=words, a_scale=words // 4, b_scale=words // 4,
                 a_sf_group0=words, b_sf_group0=words, a_sf_group1=words // 2,
                 b_sf_group1=words // 2, c_data=1, golden_result_bits=1)
    widths = dict(a_data=16, b_data=16, a_scale=8, b_scale=8,
                  a_sf_group0=1, b_sf_group0=1, a_sf_group1=1, b_sf_group1=1,
                  c_data=32, golden_result_bits=32)
    values = {}
    for key in HEX_FILES:
        rows = [int(line, 16) for line in (path / (key + '.txt')).read_text().splitlines()]
        size = sizes[key]
        if len(rows) != count * size or any(value < 0 or value >= 1 << widths[key] for value in rows):
            raise ValueError('Wrong dimensions/range: ' + str(path / key))
        values[key] = [rows[index * size:(index + 1) * size] for index in range(count)]
    values['golden_result_value'] = (path / 'golden_result_value.txt').read_text().splitlines()
    if len(values['golden_result_value']) != count:
        raise ValueError('Wrong textual golden count')
    return metadata, values


def normalize(scope, ratio, mode, source_head, raw_manifest):
    segments = ((CASE, 1024),) if scope == 'power' else SEGMENTS
    requests, expected, references, audits, source_cases = [], [], [], [], []
    for case, count in segments:
        path = RAW / scope / ratio / mode / case
        metadata, values = read_native(path, mode, ratio)
        if metadata['txn_count'] != count:
            raise ValueError('Wrong segment count')
        first = len(requests)
        exact_bits, source_bits = [], []
        logical_k = metadata['logical_k']
        for index in range(count):
            ident = len(requests)
            request, indices = request_from_source(metadata, values, index, logical_k,
                                                   ident=ident, last=False)
            exact = exact_logical(request, logical_k)
            upstream = values['golden_result_bits'][index][0]
            requests.append(request)
            exact_bits.append(exact['bits'])
            source_bits.append(upstream)
            expected.append(dict(id=ident, d=None, d_datatype=0, last=False,
                                 cmodel_result=None, cmodel_status='not_evaluated',
                                 exact_fp32_or_int32=f"{exact['bits']:08x}",
                                 exact_value=serialize_exact(exact)))
            references.append(dict(id=ident, source_case=case, source_index=index,
                                   source_logical_k=logical_k,
                                   source_fp64_fp32_bits=f'{upstream:08x}',
                                   source_value_text=values['golden_result_value'][index],
                                   comparable_to_target=True))
        audit = audit_results(source_bits, exact_bits)
        if audit['nonfinite_mismatches'] or audit['max_ulp'] > 1:
            raise ValueError('Source/exact disagreement: ' + str(audit))
        audits.append(dict(case=case, **audit))
        source_cases.append(dict(name=case, start=first, count=count,
                                 data_policy=metadata['data_policy'],
                                 scale_policy=metadata['scale_policy'], c_policy=metadata['c_policy'],
                                 seed=metadata.get('seed'), distribution=metadata.get('distribution')))
    requests[-1]['last'] = expected[-1]['last'] = True
    dataset = ('qwen3_8b_mlp_down_proj_1024' if scope == 'power'
               else ratio.replace('petile_full16_', 'petile_') + '_native_961')
    out = DEST / 'normalized' / scope / mode / f'K{logical_k}' / dataset
    if out.exists():
        raise ValueError('Refusing to replace existing normalized data: ' + str(out))
    out.mkdir(parents=True)
    write_logical_inputs(out / 'inputs.jsonl', requests, logical_k)
    for name, rows in [('expected.jsonl', expected), ('source_reference.jsonl', references)]:
        (out / name).write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
    datatype = DTYPES[mode]
    manifest = dict(schema=SCHEMA, format=mode, datatype=datatype, logical_k=logical_k,
                    count=len(requests), dataset=dataset,
                    purpose='workload_power' if scope == 'power' else 'native_functional_regression',
                    source_logical_k=logical_k, extraction='native', selected_element_range=[0, logical_k],
                    c_policy='source C unchanged; add exactly once',
                    group_elements=FORMATS[datatype][5], group_count=logical_k // FORMATS[datatype][5],
                    packed_widths=packed_widths(datatype, logical_k), segments=source_cases,
                    source_scale_indices_per_group=indices, source_ratio=ratio,
                    source_repository=dict(name='Quant_LLM_Chip_Codesign', git_head=source_head,
                                           content_identity='per-file SHA-256'),
                    source_copy_directory=str((RAW / scope / ratio / mode).relative_to(ROOT)),
                    source_copy_manifest=str(raw_manifest.relative_to(ROOT)),
                    source_copy_manifest_sha256=sha256(raw_manifest),
                    mathematical_reference='Fraction exact dequantized dot+C; one FP32 RNE conversion',
                    reference_sources={str(p.relative_to(ROOT)): sha256(p) for p in
                                       (Path(__file__), ROOT / 'test/cases/import_petile_ratio.py',
                                        ROOT / 'test/reference/exact.py', ROOT / 'test/reference/logical.py',
                                        ROOT / 'test/adapters/logical.py')},
                    source_full_k_audits=audits, cmodel_status='not_evaluated',
                    rtl_status='not_run_on_this_dataset', ppa_eligible=False,
                    files_sha256={name: sha256(out / name) for name in
                                  ('inputs.jsonl', 'expected.jsonl', 'source_reference.jsonl')})
    if scope == 'power':
        manifest['recommended_measurement'] = WINDOW
        manifest['distribution'] = metadata['distribution']
    save(out / 'manifest.json', manifest)
    if read_logical_inputs(out)[1] != requests:
        raise ValueError('Logical input round trip failed')
    result = dict(directory=str(out.relative_to(ROOT)), format=mode, logical_k=logical_k,
                  count=len(requests), purpose=manifest['purpose'],
                  source_exact_count=sum(item['bit_exact'] for item in audits),
                  source_max_ulp=max(item['max_ulp'] for item in audits),
                  manifest_sha256=sha256(out / 'manifest.json'))
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-repo', type=Path, required=True)
    parser.add_argument('--copy-only', action='store_true')
    parser.add_argument('--normalize-only', action='store_true')
    args = parser.parse_args()
    repository = args.source_repo.resolve(strict=True)
    head = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
    source = repository / RELATIVE
    batch = source / 'power_data' / BATCH
    upstream = json.loads((batch / 'manifest.json').read_text())
    case_index = {item['path']: item for item in upstream['cases']}
    manifest_path = DEST / 'raw_import_manifest.json'
    if not args.normalize_only:
        files = []
        for scope in ('functional', 'power'):
            base = source / 'petile_ratio' if scope == 'functional' else batch / 'petile_ratio'
            for ratio in RATIOS:
                for mode in Q_MODES + E_MODES:
                    for file in sorted((base / ratio / mode).rglob('*')):
                        if not file.is_file():
                            continue
                        target = RAW / scope / file.relative_to(base)
                        expected = None
                        if scope == 'power':
                            entry = case_index[str(file.parent.relative_to(batch))]
                            expected = entry['files'][file.name]
                        info = copy_verified(file, target, expected)
                        files.append(dict(source=str(file.relative_to(repository)),
                                          destination=str(target.relative_to(ROOT)), **info))
        for name, expected in {'manifest.json': sha256(batch / 'manifest.json'),
                               **upstream['source_files']}.items():
            file = batch / name
            target = RAW / 'provenance' / name
            info = copy_verified(file, target, expected)
            files.append(dict(source=str(file.relative_to(repository)),
                              destination=str(target.relative_to(ROOT)), **info))
        save(manifest_path, dict(schema_version=1, imported_at='2026-11-12 Asia/Shanghai',
                                 source_repository='Quant_LLM_Chip_Codesign', source_head=head,
                                 source_mutated=False, selection=dict(ratios=RATIOS, formats=Q_MODES + E_MODES),
                                 file_count=len(files), bytes=sum(row['bytes'] for row in files), files=files))
    if args.copy_only:
        return
    for item in json.loads(manifest_path.read_text())['files']:
        if sha256(ROOT / item['destination']) != item['sha256']:
            raise ValueError('Raw local copy changed')
    datasets = [normalize(scope, ratio, mode, head, manifest_path)
                for scope in ('functional', 'power') for ratio in RATIOS for mode in Q_MODES + E_MODES]
    save(DEST / 'import_summary.json', dict(schema_version=1, datasets=datasets,
                                          total_transactions=sum(row['count'] for row in datasets),
                                          raw_manifest_sha256=sha256(manifest_path),
                                          cmodel_evaluated=False, rtl_verified=False, power_measured=False))


if __name__ == '__main__':
    main()
