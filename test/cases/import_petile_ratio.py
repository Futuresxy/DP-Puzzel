#!/usr/bin/env python3
"""Import Q/E logical-K vectors and regenerate exact mathematical goldens.

Import native E K96/K128 and Q K64 sources without local truncation.
Source C remains unchanged and is added once after the exact dot product.
No finite-width CModel or RTL golden is claimed for unimplemented mixed tops.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

TEST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST))
from adapters.cmodel import ROOT, sha256
from adapters.logical import SCHEMA, packed_widths, normalized_request, write_logical_inputs
from cases.import_legacy import pack
from reference.exact import DTYPES, FORMATS, ulp_distance
from reference.logical import exact_logical, serialize_exact

E_MODES = ('mxfp4_e2m1', 'nvfp4', 'hif4')
Q_MODES = ('mxfp8_e4m3', 'mxfp8_e5m2', 'mxfp6_e3m2', 'mxfp6_e2m3')
SOURCE_TYPES = dict(nvfp4=0, mxfp4_e2m1=1, hif4=2, mxfp6_e2m3=3,
                    mxfp6_e3m2=4, mxfp8_e4m3=5, mxfp8_e5m2=6)
SOURCE_SCALE_TYPES = dict(nvfp4=1, hif4=3)
SEGMENTS = (('batch64_random', 64), ('batch128_mixed_random', 128),
            ('batch256_deepseek_ai_load', 256), ('batch512_ai_load', 512), ('ones', 1))
HEX_FILES = ('a_data', 'b_data', 'a_scale', 'b_scale', 'a_sf_group0', 'b_sf_group0',
             'a_sf_group1', 'b_sf_group1', 'c_data', 'golden_result_bits')


def source_scale_index(group_index, mode, layout):
    """Read the documented source layout, including unused scale array slots."""
    run_start = group_index
    while run_start and layout[run_start - 1] == layout[group_index]:
        run_start -= 1
    block_start = run_start + (group_index - run_start) // 4 * 4
    local = group_index - block_start
    if mode == 'nvfp4':
        return block_start + local
    if mode == 'mxfp4_e2m1':
        return block_start + local // 2
    return block_start  # Q K32 blocks and HiF4 K64 blocks.


def read_case(path, mode):
    metadata = json.loads((path / 'meta.json').read_text())
    words = metadata['dimk_words']
    count = metadata['txn_count']
    elements_per_word = 4 if mode in E_MODES else 2
    expected_kind = 'fp4' if mode in E_MODES and metadata['ratio_id'] != 'petile_full16_low16' else 'low'
    layout = metadata['group_layout']
    if (metadata['format'] != mode or metadata['logical_k'] != words * elements_per_word or
        metadata['elements_per_word'] != elements_per_word or metadata['active_word_count'] != words or
        metadata['dimk'] != words or metadata['group_size'] != 4 or len(layout) != words // 4 or
        layout != metadata['pegroup_layout'] or layout[:4] != ['full'] * 4 or
        layout[4:] != [expected_kind] * (len(layout) - 4) or
        metadata['a_data_type'] != SOURCE_TYPES[mode] or metadata['b_data_type'] != SOURCE_TYPES[mode] or
        metadata['a_sf_type'] != SOURCE_SCALE_TYPES.get(mode, 2) or
        metadata['b_sf_type'] != SOURCE_SCALE_TYPES.get(mode, 2) or
        metadata['c_type'] != 0 or metadata['out_type'] != 0 or metadata['rm'] != 0):
        raise ValueError(f'unsupported source metadata: {path.name}/{mode}')
    if metadata['golden_model'] != 'fp64_dequant_dot_plus_c_v1':
        raise ValueError('unexpected source golden model')
    sizes = dict(a_data=words, b_data=words, a_scale=words // 4, b_scale=words // 4,
                 a_sf_group0=words, b_sf_group0=words, a_sf_group1=words // 2,
                 b_sf_group1=words // 2, c_data=1, golden_result_bits=1)
    widths = dict(a_data=16, b_data=16, a_scale=8, b_scale=8,
                  a_sf_group0=1, b_sf_group0=1, a_sf_group1=1, b_sf_group1=1,
                  c_data=32, golden_result_bits=32)
    values = {}
    for key in HEX_FILES:
        data = [int(line, 16) for line in (path / f'{key}.txt').read_text().splitlines()]
        if len(data) != count * sizes[key] or any(value < 0 or value >= 1 << widths[key] for value in data):
            raise ValueError(f'{key}: source dimensions/range mismatch')
        values[key] = [data[index * sizes[key]:(index + 1) * sizes[key]] for index in range(count)]
    source_text = (path / 'golden_result_value.txt').read_text().splitlines()
    if len(source_text) != count:
        raise ValueError('source textual golden count mismatch')
    values['golden_result_value'] = source_text
    return metadata, values


def request_from_source(metadata, values, index, logical_k, ident=0, last=False):
    mode = metadata['format']
    datatype = DTYPES[mode]
    group_elements = FORMATS[datatype][5]
    if logical_k != metadata['logical_k'] or logical_k <= 0 or logical_k % group_elements:
        raise ValueError('import must preserve the native source K and complete groups')
    source_words = logical_k // metadata['elements_per_word']
    group_count = logical_k // group_elements
    kind = 2 if datatype == 8 else 3 if datatype == 9 else 1
    request = dict(id=ident, a_datatype=datatype, b_datatype=datatype, c_datatype=0,
                   a_scale_datatype=kind, b_scale_datatype=kind, last=last,
                   c=f"{values['c_data'][index][0]:08x}")
    scale_indices = [source_scale_index(group, mode, metadata['group_layout'])
                     for group in range(group_count)]
    for side in ('a', 'b'):
        elements = []
        for word in values[f'{side}_data'][index][:source_words]:
            width = 4 if mode in E_MODES else 8
            for slot in range(metadata['elements_per_word']):
                element = word >> (slot * width) & ((1 << width) - 1)
                if datatype in (5, 6):
                    if element >= 64:
                        raise ValueError('source FP6 payload must occupy low six bits')
                    element <<= 2
                elements.append(element)
        request[side] = pack(elements, FORMATS[datatype][4])
        scales = [values[f'{side}_scale'][index][slot] for slot in scale_indices]
        if mode == 'nvfp4' and any(value & 128 for value in scales):
            raise ValueError('source NVFP4 scale must be nonnegative E4M3')
        request[f'{side}_scale'] = pack(scales, 8)
        if mode == 'hif4':
            request[f'{side}_e1'] = pack(values[f'{side}_sf_group0'][index][:source_words], 1)
            request[f'{side}_e2'] = pack(values[f'{side}_sf_group1'][index][:source_words // 2], 1)
        else:
            # Non-HiF source metadata is present physically but must be unused/zero.
            if any(values[f'{side}_sf_group0'][index]) or any(values[f'{side}_sf_group1'][index]):
                raise ValueError('unexpected non-HiF source metadata')
            request[f'{side}_e1'] = request[f'{side}_e2'] = '0'
    return normalized_request(request, logical_k), scale_indices


def mapping():
    return [('petile_full16_fp48', E_MODES, 96, 'petile_fp48_native_961'),
            ('petile_full16_fp416', E_MODES, 128, 'petile_fp416_native_961'),
            ('petile_full16_low16', Q_MODES, 64, 'petile_low16_native_961')]


def import_ratio(source_root, destination=None):
    source_root = Path(source_root).resolve(strict=True)
    destination = Path(destination or TEST / 'data/dp')
    source_repo = Path(subprocess.check_output(['git', '-C', str(source_root), 'rev-parse', '--show-toplevel'], text=True).strip())
    source_head = subprocess.check_output(['git', '-C', str(source_root), 'rev-parse', 'HEAD'], text=True).strip()
    relative_source = str(source_root.relative_to(source_repo))
    cache = {}
    directories = []
    golden_sources = {str(path.relative_to(ROOT)): sha256(path) for path in
                      [TEST / 'reference/exact.py', TEST / 'reference/logical.py',
                       TEST / 'adapters/logical.py', Path(__file__)]}
    for ratio, modes, logical_k, dataset in mapping():
        for mode in modes:
            requests, expected, source_reference, segments, sources = [], [], [], [], []
            audits = dict(count=0, bit_exact=0, finite_max_ulp=0, nonfinite_mismatches=0)
            for case, declared_count in SEGMENTS:
                path = source_root / ratio / mode / case
                if path not in cache:
                    metadata, values = read_case(path, mode)
                    if metadata['txn_count'] != declared_count:
                        raise ValueError('unexpected case count')
                    full_references = []
                    for index in range(declared_count):
                        full, _ = request_from_source(metadata, values, index, metadata['logical_k'])
                        full_references.append(exact_logical(full, metadata['logical_k']))
                    cache[path] = metadata, values, full_references
                metadata, values, full_references = cache[path]
                if metadata['logical_k'] != logical_k:
                    raise ValueError('source K changed; review mapping before import')
                first = len(requests)
                for index in range(declared_count):
                    ident = len(requests)
                    request, scale_indices = request_from_source(metadata, values, index, logical_k,
                                                                 ident=ident, last=ident == 960)
                    exact = full_references[index]
                    upstream_bits = values['golden_result_bits'][index][0]
                    full_bits = full_references[index]['bits']
                    distance = ulp_distance(full_bits, upstream_bits)
                    audits['count'] += 1
                    audits['bit_exact'] += full_bits == upstream_bits
                    if distance is None:
                        audits['nonfinite_mismatches'] += 1
                    else:
                        audits['finite_max_ulp'] = max(audits['finite_max_ulp'], distance)
                    requests.append(request)
                    expected.append(dict(id=ident, d=None, d_datatype=0, last=request['last'],
                                         cmodel_result=None, cmodel_status='not_implemented',
                                         exact_fp32_or_int32=f"{exact['bits']:08x}",
                                         exact_value=serialize_exact(exact)))
                    source_reference.append(dict(id=ident, source_case=case, source_index=index,
                                                 source_logical_k=metadata['logical_k'],
                                                 source_fp64_fp32_bits=f'{upstream_bits:08x}',
                                                 source_value_text=values['golden_result_value'][index],
                                                 source_full_exact_fp32=f'{full_bits:08x}',
                                                 comparable_to_target=True))
                segments.append(dict(name=case, start=first, count=declared_count, seed=metadata.get('seed'),
                                     data_policy=metadata['data_policy'], scale_policy=metadata['scale_policy'],
                                     c_policy=metadata['c_policy']))
                filenames = ['meta.json', *(f'{key}.txt' for key in HEX_FILES), 'golden_result_value.txt']
                sources.append(dict(case=case, files={name: dict(path=str((path / name).relative_to(source_repo)),
                                                               sha256=sha256(path / name)) for name in filenames}))
            out = destination / mode / f'K{logical_k}' / dataset
            if out.exists() and any(out.iterdir()):
                old = json.loads((out / 'manifest.json').read_text())
                if old.get('schema') != SCHEMA or old.get('format') != mode or old.get('logical_k') != logical_k:
                    raise ValueError('refusing to overwrite unrelated dataset')
            out.mkdir(parents=True, exist_ok=True)
            write_logical_inputs(out / 'inputs.jsonl', requests, logical_k)
            for name, rows in [('expected.jsonl', expected), ('source_reference.jsonl', source_reference)]:
                (out / name).write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
            datatype = DTYPES[mode]
            manifest = dict(schema=SCHEMA, format=mode, datatype=datatype, logical_k=logical_k,
                            count=len(requests), dataset=dataset, source_logical_k=metadata['logical_k'],
                            extraction='native',
                            selected_element_range=[0, logical_k], c_policy='source C unchanged; add exactly once',
                            group_elements=FORMATS[datatype][5], group_count=logical_k // FORMATS[datatype][5],
                            packed_widths=packed_widths(datatype, logical_k), segments=segments,
                            source_scale_indices_per_group=scale_indices,
                            source_repository=dict(name=source_repo.name, git_head=source_head,
                                                   content_identity='per-file SHA-256; HEAD alone does not identify generated corpus'),
                            source_root=relative_source, source_ratio=ratio, sources=sources,
                            mathematical_reference='Fraction exact dequantized dot+C; one FP32 RNE conversion',
                            mathematical_reference_sources=golden_sources,
                            cmodel_status='not_implemented', rtl_status='not_implemented', ppa_eligible=False,
                            source_golden_model=metadata['golden_model'], source_full_k_audit=audits,
                            input_layout='test/data/README.md#逻辑-k-扩展数据-dp_logical_vectors_v1',
                            files_sha256={name: sha256(out / name) for name in
                                          ('inputs.jsonl', 'expected.jsonl', 'source_reference.jsonl')})
            (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
            for file in out.iterdir():
                if file.stat().st_size > 5 * 1024 * 1024:
                    raise ValueError(f'file exceeds repository limit: {file.name}')
            directories.append(out)
            print(f'{mode} K{logical_k} {dataset}: {len(requests)} mathematical goldens; '
                  f'source K{metadata["logical_k"]} exact/FP64 audit={audits}', flush=True)
    return directories


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path, help='read-only petile_ratio directory')
    parser.add_argument('--dest-root', type=Path, default=TEST / 'data/dp')
    args = parser.parse_args()
    import_ratio(args.source_root, args.dest_root)
