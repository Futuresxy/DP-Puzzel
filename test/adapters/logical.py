"""Dimension-explicit Q/E vectors for proposed mixed DP profiles.

This data schema deliberately has no hardware K_FP16 field. Existing DP_INPUTS_V1
CModel/RTL runners do not consume inputs.jsonl or math-only expected.jsonl files.
"""
import json
from pathlib import Path

from adapters.cmodel import FIELDS
from reference.exact import FORMATS
from reference.logical import Q_TYPES, E_TYPES

SCHEMA = 'dp_logical_vectors_v1'


def packed_widths(datatype, logical_k):
    if datatype not in Q_TYPES + E_TYPES:
        raise ValueError('only Q/E logical vectors are supported')
    group_elements = FORMATS[datatype][5]
    if logical_k <= 0 or logical_k % group_elements:
        raise ValueError('logical K must contain complete Q8/E16 groups')
    groups = logical_k // group_elements
    return dict(a=logical_k * FORMATS[datatype][4], b=logical_k * FORMATS[datatype][4],
                c=32, a_scale=8 * groups, b_scale=8 * groups,
                a_e1=4 * groups, b_e1=4 * groups, a_e2=2 * groups, b_e2=2 * groups)


def validate_request(request, logical_k):
    if set(request) != set(FIELDS):
        raise ValueError('logical request field set mismatch')
    datatype = request['a_datatype']
    widths = packed_widths(datatype, logical_k)
    if request['b_datatype'] != datatype or request['c_datatype'] != 0:
        raise ValueError('logical vectors require same-format Q/E A/B and FP32 C')
    kind = 2 if datatype == 8 else 3 if datatype == 9 else 1
    if request['a_scale_datatype'] != kind or request['b_scale_datatype'] != kind:
        raise ValueError('scale datatype mismatch')
    if type(request['id']) is not int or request['id'] < 0 or type(request['last']) is not bool:
        raise ValueError('invalid id/last')
    for field, width in widths.items():
        value = request[field]
        if not isinstance(value, str) or len(value) != (width + 3) // 4:
            raise ValueError(f'{field}: wrong fixed hexadecimal width')
        if any(character not in '0123456789abcdef' for character in value):
            raise ValueError(f'{field}: lowercase hexadecimal required')
        if int(value, 16) >= 1 << width:
            raise ValueError(f'{field}: nonzero unused high bits')
    for side in ('a', 'b'):
        if datatype != 9 and (int(request[f'{side}_e1'], 16) or int(request[f'{side}_e2'], 16)):
            raise ValueError('unexpected HiF4 metadata')
        if datatype in (5, 6):
            packed = int(request[side], 16)
            if any((packed >> (index * 8)) & 3 for index in range(logical_k)):
                raise ValueError('FP6 must occupy the high six bits of each byte')
    return request


def normalized_request(request, logical_k):
    result = dict(request)
    for field, width in packed_widths(request['a_datatype'], logical_k).items():
        value = int(request[field], 16)
        if value < 0 or value >= 1 << width:
            raise ValueError(f'{field}: value out of range')
        result[field] = f'{value:0{(width + 3) // 4}x}'
    return validate_request(result, logical_k)


def write_logical_inputs(path, requests, logical_k):
    rows = [normalized_request(request, logical_k) for request in requests]
    if [row['id'] for row in rows] != list(range(len(rows))):
        raise ValueError('ids must be contiguous from zero')
    Path(path).write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))


def read_logical_inputs(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['schema'] != SCHEMA:
        raise ValueError('bad logical vector schema')
    logical_k = manifest['logical_k']
    rows = [validate_request(json.loads(line), logical_k)
            for line in (directory / 'inputs.jsonl').read_text().splitlines()]
    if len(rows) != manifest['count'] or [row['id'] for row in rows] != list(range(len(rows))):
        raise ValueError('logical vector count/id mismatch')
    if any(row['a_datatype'] != manifest['datatype'] for row in rows):
        raise ValueError('logical vector format mismatch')
    if manifest['packed_widths'] != packed_widths(manifest['datatype'], logical_k):
        raise ValueError('manifest width mismatch')
    return logical_k, rows
