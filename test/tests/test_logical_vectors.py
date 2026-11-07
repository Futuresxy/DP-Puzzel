"""Dimension, source-layout and exact-golden checks for mixed-DP data preparation."""
from fractions import Fraction
import json
from pathlib import Path
import random
import struct
import sys
import unittest

TEST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST))
from adapters.cmodel import DEFAULT_CONFIG, sha256, read_inputs
from adapters.logical import read_logical_inputs, normalized_request, packed_widths, validate_request
from cases.common import random_request
from cases.import_legacy import pack
from cases.import_petile_ratio import E_MODES, Q_MODES, request_from_source, source_scale_index
from reference.exact import DTYPES, FORMATS, finite, fp32, reference
from reference.logical import exact_logical


def ones(mode, logical_k):
    datatype = DTYPES[mode]
    code = dict(mxfp8_e4m3=0x38, mxfp8_e5m2=0x3c, mxfp6_e3m2=0x0c << 2,
                mxfp6_e2m3=0x08 << 2, mxfp4_e2m1=2, nvfp4=2, hif4=4)[mode]
    groups = logical_k // FORMATS[datatype][5]
    kind = 2 if mode == 'nvfp4' else 3 if mode == 'hif4' else 1
    unit_scale = 0x38 if kind == 2 else 0xc0 if kind == 3 else 127
    request = dict(id=0, a_datatype=datatype, b_datatype=datatype, c_datatype=0,
                   a_scale_datatype=kind, b_scale_datatype=kind, last=True,
                   a=pack([code] * logical_k, FORMATS[datatype][4]),
                   b=pack([code] * logical_k, FORMATS[datatype][4]), c='3f800000',
                   a_scale=pack([unit_scale] * groups, 8), b_scale=pack([unit_scale] * groups, 8),
                   a_e1='0', a_e2='0', b_e1='0', b_e2='0')
    return normalized_request(request, logical_k)


class LogicalVectors(unittest.TestCase):
    def test_known_ones_and_last_hif_metadata(self):
        for mode in E_MODES + Q_MODES:
            for logical_k in ((96, 128) if mode in E_MODES else (64,)):
                with self.subTest(mode=mode, k=logical_k):
                    result = exact_logical(ones(mode, logical_k), logical_k)
                    self.assertEqual(result['value'].value, logical_k + 1)
                    self.assertEqual(result['bits'], fp32(finite(logical_k + 1)))
        request = ones('hif4', 96)
        request['a_e1'] = format(1 << 23, '06x')
        request['a_e2'] = format(1 << 11, '03x')
        # Last 8 products: four become 2, last four become 4; +16 to dot.
        self.assertEqual(exact_logical(request, 96)['value'].value, 113)

    def test_source_scale_layout_and_fp6_pack(self):
        layout = ['full'] * 4 + ['fp4'] * 8
        self.assertEqual([source_scale_index(i, 'mxfp4_e2m1', layout) for i in range(12)],
                         [0, 0, 1, 1, 4, 4, 5, 5, 8, 8, 9, 9])
        self.assertEqual([source_scale_index(i, 'hif4', layout) for i in range(8)],
                         [0, 0, 0, 0, 4, 4, 4, 4])
        self.assertEqual([source_scale_index(i, 'nvfp4', layout) for i in range(8)], list(range(8)))
        metadata = dict(format='mxfp6_e3m2', logical_k=64, elements_per_word=2,
                        group_layout=['full'] * 4 + ['low'] * 4)
        values = dict(c_data=[[0x3f800000]])
        for side in ('a', 'b'):
            values[f'{side}_data'] = [[0x0c0c] * 32]
            values[f'{side}_scale'] = [[127, 1, 2, 3, 128, 5, 6, 7]]
            values[f'{side}_sf_group0'] = [[0] * 32]
            values[f'{side}_sf_group1'] = [[0] * 16]
        request, indices = request_from_source(metadata, values, 0, 64)
        self.assertEqual(request['a'], '30' * 64)
        self.assertEqual(indices, [0] * 4 + [4] * 4)
        # First 32 products have scale 1*1, last 32 scale 2*2; C=1.
        self.assertEqual(exact_logical(request, 64)['value'].value, 161)

    def test_native_k96_and_c_is_once(self):
        metadata = dict(format='nvfp4', logical_k=96, elements_per_word=4,
                        group_layout=['full'] * 4 + ['fp4'] * 2)
        values = dict(c_data=[[0x3f800000]])
        for side in ('a', 'b'):
            values[f'{side}_data'] = [[0x2222] * 24]
            values[f'{side}_scale'] = [[0x38] * 6]
            values[f'{side}_sf_group0'] = [[0] * 24]
            values[f'{side}_sf_group1'] = [[0] * 12]
        request, _ = request_from_source(metadata, values, 0, 96)
        self.assertEqual(exact_logical(request, 96)['value'].value, 97)
        with self.assertRaisesRegex(ValueError, 'native source K'):
            request_from_source(metadata, values, 0, 64)

    def test_special_values_and_unsigned_scale(self):
        request = ones('mxfp8_e5m2', 64)
        request['a'] = '00' * 63 + '7c'  # +Inf * 0 in element 0.
        request['b'] = '00' * 64
        result = exact_logical(request, 64)
        self.assertEqual(result['bits'], 0x7fc00000)
        self.assertTrue(result['value'].invalid)
        request['a'] = '00' * 62 + 'fc7c'
        request['b'] = '00' * 62 + '3c3c'
        self.assertTrue(exact_logical(request, 64)['value'].invalid)
        request = ones('nvfp4', 128)
        request['a_scale'] = 'b8' * 8  # E4M3 scale bit 7 is ignored, not a sign.
        self.assertEqual(exact_logical(request, 128)['value'].value, 129)
        request = ones('hif4', 96)
        request['a'] = '8' * 96
        request['b'] = '0' * 96
        request['c'] = '80000000'
        self.assertEqual(exact_logical(request, 96)['bits'], 0x80000000)

    def test_c_and_scale_special_values(self):
        for c_bits, kind, negative, invalid in (
                ('7f800000', 'inf', False, False), ('ff800000', 'inf', True, False),
                ('7fc00000', 'nan', False, False), ('7f800001', 'nan', False, True)):
            request = ones('hif4', 96)
            request['c'] = c_bits
            value = exact_logical(request, 96)['value']
            self.assertEqual((value.kind, value.negative, value.invalid), (kind, negative, invalid))
        for mode in E_MODES + Q_MODES:
            logical_k = 96 if mode in E_MODES else 64
            request = ones(mode, logical_k)
            # Canonical scale NaN: unsigned E4M3 0x7f; E8M0/E6M2 0xff.
            request['a_scale'] = request['a_scale'][:-2] + ('7f' if mode == 'nvfp4' else 'ff')
            result = exact_logical(request, logical_k)
            self.assertEqual(result['bits'], 0x7fc00000)
            self.assertFalse(result['value'].invalid)

    def test_existing_exact_reference_agreement(self):
        rng = random.Random(0xD796128)
        for k_fp16 in (4, 8, 16):
            for mode in E_MODES + Q_MODES:
                for index in range(12):
                    request = random_request(mode, rng, k_fp16, index)
                    logical_k = k_fp16 // 4 * FORMATS[DTYPES[mode]][5]
                    current = exact_logical(request, logical_k)
                    previous = reference(request, DEFAULT_CONFIG | dict(k_fp16=k_fp16))
                    self.assertEqual(current['bits'], previous['bits'])
                    self.assertEqual(current['value'], previous['value'])

    def test_malformed_layout_rejected(self):
        request = ones('mxfp6_e3m2', 64)
        request['a'] = request['a'][:-2] + '31'
        with self.assertRaisesRegex(ValueError, 'high six bits'):
            validate_request(request, 64)
        with self.assertRaises(ValueError):
            packed_widths(DTYPES['nvfp4'], 97)
        request = ones('nvfp4', 96)
        request['a'] += '0'
        with self.assertRaises(ValueError):
            validate_request(request, 96)

    def test_corpus_hashes_shapes_and_exact_results(self):
        paths = sorted((TEST / 'data/dp').glob('*/K*/petile_*_961/manifest.json'))
        self.assertEqual(len(paths), 10)
        total = 0
        for path in paths:
            manifest = json.loads(path.read_text())
            with self.subTest(path=str(path.relative_to(TEST))):
                for name, expected_hash in manifest['files_sha256'].items():
                    self.assertEqual(sha256(path.parent / name), expected_hash)
                logical_k, requests = read_logical_inputs(path.parent)
                expected = [json.loads(line) for line in (path.parent / 'expected.jsonl').read_text().splitlines()]
                self.assertEqual(len(requests), 961)
                self.assertEqual(len(expected), 961)
                self.assertEqual(manifest['source_logical_k'], logical_k)
                self.assertEqual(manifest['extraction'], 'native')
                self.assertNotIn('fp432', manifest['source_ratio'])
                self.assertEqual([part['count'] for part in manifest['segments']], [64, 128, 256, 512, 1])
                for filename, expected_hash in manifest['mathematical_reference_sources'].items():
                    self.assertEqual(sha256(TEST.parent / filename), expected_hash)
                self.assertEqual(sum(request['last'] for request in requests), 1)
                self.assertTrue(requests[-1]['last'])
                for request, golden in zip(requests, expected):
                    self.assertEqual(golden['id'], request['id'])
                    self.assertIsNone(golden['d'])
                    self.assertIsNone(golden['cmodel_result'])
                    self.assertEqual(golden['cmodel_status'], 'not_implemented')
                    result = exact_logical(request, logical_k)
                    self.assertEqual(f"{result['bits']:08x}", golden['exact_fp32_or_int32'])
                    exact = golden['exact_value']
                    self.assertEqual(result['value'].kind, exact['kind'])
                    self.assertEqual(result['value'].invalid, exact['invalid'])
                    self.assertEqual(result['value'].negative, exact['negative'])
                    if exact['kind'] == 'finite':
                        self.assertEqual(result['value'].value,
                                         Fraction(int(exact['numerator']), int(exact['denominator'])))
                total += len(requests)
        self.assertEqual(total, 9610)

    def test_upstream_fp64_rounding_differences(self):
        # Independent distance-to-FP32 proof: do not call reference.fp32 here.
        # Binary64 can lose the tiny residual around an FP32 midpoint and then
        # choose the even neighbor, unlike one direct exact-to-FP32 rounding.
        mismatches = 0
        for path in sorted((TEST / 'data/dp').glob('*/K*/petile_*_961/manifest.json')):
            expected = [json.loads(line) for line in (path.parent / 'expected.jsonl').read_text().splitlines()]
            upstream = [json.loads(line) for line in (path.parent / 'source_reference.jsonl').read_text().splitlines()]
            for golden, source in zip(expected, upstream):
                exact_bits = golden['exact_fp32_or_int32']
                upstream_bits = source['source_fp64_fp32_bits']
                if exact_bits == upstream_bits:
                    continue
                mismatches += 1
                with self.subTest(dataset=str(path.parent), id=golden['id']):
                    value = golden['exact_value']
                    exact = Fraction(int(value['numerator']), int(value['denominator']))
                    nearest = Fraction.from_float(struct.unpack('>f', bytes.fromhex(exact_bits))[0])
                    other = Fraction.from_float(struct.unpack('>f', bytes.fromhex(upstream_bits))[0])
                    self.assertEqual(abs(int(exact_bits, 16) - int(upstream_bits, 16)), 1)
                    self.assertLess(abs(exact - nearest), abs(exact - other))
                    self.assertEqual(Fraction.from_float(float(exact)), (nearest + other) / 2)
                    self.assertEqual(int(upstream_bits, 16) & 1, 0)
                    self.assertEqual(struct.pack('>f', float(exact)).hex(), upstream_bits)
        self.assertEqual(mismatches, 8)

    def test_existing_runners_still_see_only_original_inputs(self):
        paths = sorted((TEST / 'data/dp').glob('*/*/*/inputs.txt'))
        self.assertEqual(len(paths), 11)
        count = 0
        for path in paths:
            k, requests = read_inputs(path)
            self.assertEqual(k, 16)
            count += len(requests)
        self.assertEqual(count, 10747)


if __name__ == '__main__':
    unittest.main()
