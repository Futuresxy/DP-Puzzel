"""Guard against double counting and silent loss in functional power accounting."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/summarize_functional_power.py'
spec = importlib.util.spec_from_file_location('functional_accounting', SCRIPT)
accounting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accounting)


class LeafReportTest(unittest.TestCase):
    def parse(self, rows, names):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cells.rpt'
            path.write_text('Dynamic Power Units = 1mW\nLeakage Power Units = 1nW\n' + rows)
            return accounting.read_power(path, set(names))

    def test_no_hierarchy_or_net_double_count(self):
        result = self.parse('group 8 4 12 (100%) 900\n'
                            'group/U1 2 1 3 (66%) 40\n'
                            'group/net 1 (100%)\n', ['group/U1'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result['group/U1']['dynamic_mw'], 3)
        self.assertAlmostEqual(result['group/U1']['leakage_mw'], 40e-6)

    def test_missing_leaf_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('U1 2 1 3 (66%) 40\n', ['U1', 'U2'])

    def test_duplicate_leaf_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('U1 2 1 3 (66%) 40\n' * 2, ['U1'])

    def test_characterized_negative_internal_is_not_clamped(self):
        result = self.parse('U1 -1e-9 0 -1e-9 (100%) 0.46\n', ['U1'])
        self.assertEqual(result['U1']['internal_mw'], -1e-9)

    def test_icg_not_counted_as_unpack_register(self):
        name = 'group/lane/u_lane_unpack/clk_gate_ff_s0_s1_mantissas/latch'
        self.assertEqual(accounting.classify(name, True),
                         (accounting.OTHER, 'Clock gating cells', 'icg'))

    def test_same_field_different_hierarchy_has_different_owner(self):
        field = 'ff_s3_s4_out_anchor_ff_storage_out_q_reg_0_'
        lane = accounting.classify('g_group_0__u_group_unit/g_lane_0__u_lane/' + field, True)
        group = accounting.classify('g_group_0__u_group_unit/' + field, True)
        self.assertEqual(lane[0], accounting.ALIGN)
        self.assertEqual(group[0], accounting.EXP)

    def test_unknown_inline_cells_stay_unattributed(self):
        self.assertEqual(accounting.classify('g_group_0__u_group_unit/U500', False)[0],
                         accounting.OTHER)


if __name__ == '__main__':
    unittest.main()
