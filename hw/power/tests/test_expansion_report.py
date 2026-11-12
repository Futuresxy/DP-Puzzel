"""Prevent incomplete or non-native workloads from entering expansion reports."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report_expansion_power import check_scope


class ExpansionReportScopeTests(unittest.TestCase):
    def points(self, top='dp_top_t8h16q64e64', q=64, e=64):
        return [dict(top=top, format=mode, logical_k=k) for mode, k in
                [('bf16', 16), ('mxfp8_e4m3', q), ('mxfp4_e2m1', e)]]

    def test_complete_single_or_multiple_profiles(self):
        check_scope(self.points())
        check_scope(self.points() + self.points('dp_top_t8h16q32e192', 32, 192)
                    + self.points('dp_top_t8h16q32e256', 32, 256)
                    + self.points('dp_top_t8h16q96e192', 96, 192)
                    + self.points('dp_top_t8h16q128e256', 128, 256))

    def test_partial_duplicate_unknown_or_wrong_k_rejected(self):
        invalid = [[], self.points()[:2], self.points() + self.points(),
                   self.points('dp_top'), self.points(e=128)]
        for points in invalid:
            with self.subTest(points=points), self.assertRaises(ValueError):
                check_scope(points)


if __name__ == '__main__':
    unittest.main()
