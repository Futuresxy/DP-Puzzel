"""Independent rational checks for exact arithmetic, RNE and the random TXT corpus."""
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'hw/test/vectors'))
sys.path.insert(0, str(ROOT / 'hw/test/flow'))
sys.path.insert(0, str(ROOT / 'hw/test/reference'))
from exact_dot import (FORMATS, FP32, NAN, ONE, ZERO, Dyadic, Operand,
                       decode_binary, decode_element, decode_scale, dequantize,
                       dot_product, exact_sum, finite, golden_fp32, multiply,
                       round_fp32, serialize, shape)
from generate_random_vectors import (AB_SCENARIOS, C_SCENARIOS, DATASET,
                                     generate, unit_operand)
from pe_vectors import validate_case
from fp32_compare import compare_random_case


def rational(value):
    if value.special:
        raise ValueError('expected finite reference')
    return Fraction(value.coefficient) * Fraction(2) ** value.exponent


def fp32_fraction(raw):
    sign = -1 if raw & 0x80000000 else 1
    exponent, fraction = (raw >> 23) & 255, raw & 0x7FFFFF
    return sign * Fraction(fraction if exponent == 0 else (1 << 23) + fraction) * Fraction(2) ** (exponent - 150 if exponent else -149)


def rational_rne(value):
    """Independent oracle: binary-search all finite positive FP32 encodings.

    This searches representable rationals and compares distances; it does not
    reuse the DUT-independent golden's integer shifting/round-bit algorithm.
    """
    sign = 0x80000000 if value < 0 else 0
    value = abs(value)
    overflow_midpoint = Fraction(2) ** 128 - Fraction(2) ** 103
    if value >= overflow_midpoint:
        return sign | 0x7F800000
    lo, hi = 0, 0x7F7FFFFF
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fp32_fraction(mid) <= value:
            lo = mid
        else:
            hi = mid - 1
    choices = (lo, min(lo + 1, 0x7F7FFFFF))
    return sign | min(choices, key=lambda bits: (abs(fp32_fraction(bits) - value), bits & 1))


class ExactArithmeticTests(unittest.TestCase):
    def test_low_precision_codebooks_and_specials(self):
        for name in FORMATS:
            fmt = FORMATS[name]
            if fmt.bits > 8 or name == 'hif4':
                continue
            for raw in range(1 << fmt.bits):
                sign = -1 if raw >> (fmt.bits - 1) else 1
                exponent = (raw >> fmt.frac_bits) & ((1 << fmt.exp_bits) - 1)
                fraction = raw & ((1 << fmt.frac_bits) - 1)
                decoded = decode_element(name, raw)
                if fmt.specials == 'ieee' and exponent == (1 << fmt.exp_bits) - 1:
                    self.assertEqual(decoded.special, 'nan' if fraction else 'inf')
                elif fmt.specials == 'nan_only' and (raw & ((1 << (fmt.bits-1))-1)) == (1 << (fmt.bits-1))-1:
                    self.assertEqual(decoded.special, 'nan')
                else:
                    significand = Fraction(fraction, 1 << fmt.frac_bits) + (exponent != 0)
                    expected = sign * significand * Fraction(2) ** (max(exponent, 1) - fmt.bias)
                    self.assertEqual(rational(decoded), expected, (name, raw))
        for raw in range(16):
            for g0 in (0, 1):
                for g1 in (0, 1):
                    self.assertEqual(rational(decode_element('hif4', raw, g0, g1)),
                                     (-1 if raw & 8 else 1) * Fraction(raw & 7, 4) * 2 ** (g0 + g1))

    def test_scale_encodings_including_zero_code_and_nan(self):
        for raw in range(255):
            self.assertEqual(rational(decode_scale('e8m0', raw)), Fraction(2) ** (raw - 127))
            self.assertEqual(rational(decode_scale('e6m2', raw)),
                             (1 + Fraction(raw & 3, 4)) * Fraction(2) ** ((raw >> 2) - 48))
        self.assertEqual(decode_scale('e8m0', 255), NAN)
        self.assertEqual(decode_scale('e6m2', 255), NAN)
        self.assertEqual(decode_scale('ue4m3', 0), ZERO)
        self.assertEqual(decode_scale('ue4m3', 0x7F), NAN)
        self.assertEqual(rational(decode_scale('ue4m3', 0x7E)), 448)
        with self.assertRaises(ValueError):
            decode_scale('ue4m3', 0x80)

    def test_rne_ties_normal_subnormal_and_overflow(self):
        cases = [
            (finite((1 << 24) + 1, -24), 0x3F800000),
            (finite((1 << 24) + 3, -24), 0x3F800002),
            (finite(1, -150), 0), (finite(-1, -150), 0x80000000),
            (finite(3, -150), 2), (finite(5, -150), 2),
            (finite((1 << 24) - 1, -150), 0x00800000),
            (finite((1 << 25) - 1, 103), 0x7F800000),
            (finite(((1 << 25) - 1) * 2 - 1, 102), 0x7F7FFFFF),
        ]
        for value, bits in cases:
            self.assertEqual(round_fp32(value), bits)
        # BF16 A=B=[1,2^-12,2^-27,0...] is a double-rounding counterexample.
        exact = exact_sum((ONE, finite(1, -24), finite(1, -54)))
        self.assertEqual(round_fp32(exact), 0x3F800001)

    def test_rne_against_independent_rational_search(self):
        rng = random.Random(0xDA2027)
        for _ in range(1000):
            value = finite(rng.choice((-1, 1)) * rng.getrandbits(rng.randint(1, 140)), rng.randint(-350, 160))
            self.assertEqual(round_fp32(value), rational_rne(rational(value)), value)
        # Exhaustive half-precision finite inputs; every one is exactly representable in FP32.
        fmt = FORMATS['fp16']
        for raw in range(1 << 16):
            if (raw >> 10) & 31 != 31:
                value = decode_binary(fmt, raw)
                self.assertEqual(fp32_fraction(round_fp32(value)), rational(value))

    def test_exact_sum_product_and_nonfinite_precedence(self):
        huge = finite(1, 400)
        self.assertEqual(exact_sum((huge, finite(3, -300), -huge)), finite(3, -300))
        pos, neg = Dyadic(1, special='inf'), Dyadic(-1, special='inf')
        self.assertEqual(multiply(ZERO, pos), NAN)
        self.assertEqual(exact_sum((pos, neg)), NAN)
        self.assertEqual(exact_sum((pos, NAN)), NAN)
        self.assertEqual(round_fp32(pos), 0x7F800000)
        self.assertEqual(round_fp32(neg), 0xFF800000)
        self.assertEqual(round_fp32(NAN), 0x7FC00000)

    def test_hif4_group_indexing_and_partial_64_lane_block(self):
        a, b = unit_operand('hif4', 96), unit_operand('hif4', 96)
        a.scales[1] = 0xC4  # second, partial 64-lane block: scale=2
        a.group0[16] = 1
        a.group1[8] = 1
        self.assertEqual(rational(dot_product('hif4', a, b)), 160)
        self.assertEqual(golden_fp32('hif4', a, b, 0), 0x43200000)
        for name in FORMATS:
            k = 32
            left, right = unit_operand(name, k), unit_operand(name, k)
            self.assertEqual(rational(dot_product(name, left, right)), k)
        with self.assertRaises(ValueError):
            shape('mxfp8_e4m3', 31)
        with self.assertRaises(ValueError):
            shape('hif4', 95)


class GeneratedCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / 'corpus'
        cls.index = generate(cls.root, list(FORMATS), [32], seed=24301)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def case(self, name):
        return self.root / name / 'K32' / DATASET

    def test_nine_formats_counts_strata_and_exact_redecode(self):
        self.assertEqual(self.index['case_count'], 9)
        for name in FORMATS:
            m = validate_case(self.case(name))
            labels = m['scenario_by_transaction']
            self.assertEqual(Counter(labels[:1024]), {s:128 for s in AB_SCENARIOS})
            self.assertEqual(Counter(labels[1088:]), {s:64 for s in C_SCENARIOS})
            self.assertEqual(len(labels[1024:1088]), 64)
            self.assertTrue(all(not x['special'] for x in m['exact_results'][:1024]))
            self.assertTrue(all(not x['special'] for x in m['exact_results'][1088:]))
            for i, label in enumerate(labels):
                if label == 'c_exact_cancellation':
                    self.assertEqual(m['exact_results'][i], serialize(ZERO))
                if label == 'c_near_cancellation':
                    self.assertNotEqual(m['exact_results'][i]['coefficient'], '0')
            special_goldens = (self.case(name)/'golden.txt').read_text().splitlines()[1024:1088]
            self.assertTrue({'00000000','7fc00000','7f800000','ff800000'} <= set(special_goldens))

    def test_seed_selection_stability_and_no_overwrite(self):
        other = Path(self.temporary.name) / 'other'
        generate(other, ['hif4'], [32], seed=24301)
        for filename in ('inputs.txt','golden.txt','case.json'):
            self.assertEqual((self.case('hif4')/filename).read_bytes(),
                             (other/'hif4/K32'/DATASET/filename).read_bytes())
        with self.assertRaises(ValueError):
            generate(other, ['hif4'], [32])

    def test_tampered_golden_and_relabelled_segment_are_rejected(self):
        target = Path(self.temporary.name) / 'tampered'
        shutil.copytree(self.case('fp16'), target)
        golden = target/'golden.txt'
        lines = golden.read_text().splitlines()
        lines[0] = f'{int(lines[0],16)^1:08x}'
        golden.write_text('\n'.join(lines)+'\n')
        with self.assertRaises(ValueError):
            validate_case(target)
        shutil.copyfile(self.case('fp16')/'golden.txt', golden)
        meta = json.loads((target/'case.json').read_text())
        meta['segments'][1]['require_bit_exact'] = False
        (target/'case.json').write_text(json.dumps(meta))
        with self.assertRaises(ValueError):
            validate_case(target)

    def test_two_step_acceptance_is_inclusive_and_exact_rate_is_only_statistic(self):
        segments = [dict(dataset='ordinary',start=0,stop=4,count=4,
                         include_in_precision_rate=True,require_bit_exact=False),
                    dict(dataset='directed',start=4,stop=5,count=1,
                         include_in_precision_rate=False,require_bit_exact=True)]
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            golden, actual = root/'golden', root/'actual'
            golden.write_text('3f800000\n'*4+'00000000\n')
            actual.write_text('3f800002\n'*4+'00000000\n')
            self.assertTrue(compare_random_case(actual,golden,segments,root)['passed'])
            actual.write_text('3f800003\n'+'3f800000\n'*3+'00000000\n')
            self.assertFalse(compare_random_case(actual,golden,segments,root)['passed'])
            actual.write_text('3f800000\n'*4+'80000000\n')
            self.assertFalse(compare_random_case(actual,golden,segments,root)['passed'])
            # Numerical ordering crosses signed zero without an artificial extra step.
            golden.write_text('80000001\n'*4+'7fc00000\n')
            actual.write_text('00000001\n'*4+'7fc00000\n')
            self.assertTrue(compare_random_case(actual,golden,segments,root)['passed'])
            actual.write_text('00000001\n'*4+'7fc00001\n')
            self.assertFalse(compare_random_case(actual,golden,segments,root)['passed'])


if __name__ == '__main__':
    unittest.main()
