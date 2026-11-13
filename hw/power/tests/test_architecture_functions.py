"""Exercise exclusive seven-function ownership at mapped hardware boundaries.

Synthetic library functions and tiny structural netlists keep tests independent
of proprietary cells. Tests check the numerical accounting, not physical naming
specific to the N12 library.
"""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import report_architecture_functions as accounting


LIBRARY = ('reference\tpin\tdirection\tfunction\n'
           'BUF\tA\tin\t\nBUF\tY\tout\tA\n')


class FunctionOwnershipTests(unittest.TestCase):
    def assign(self, netlist, names, top='dp_top', sequential=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'netlist.v').write_text(netlist)
            (root / 'library.tsv').write_text(LIBRARY)
            leaves = {name: dict(sequential='true' if name in sequential else 'false',
                                 area_um2='1.25') for name in names}
            return accounting.assign_cells(root / 'netlist.v', root / 'library.tsv', top, leaves)

    def test_exponent_register_precedes_product_name(self):
        owner, _ = accounting.register_owner('ff_s1_s2_product_exponents_ff_storage_out_q_reg_0_')
        self.assertEqual(owner, accounting.EXP)
        owner, _ = accounting.register_owner('ff_s1_s2_product_magnitudes_ff_storage_out_q_reg_0_')
        self.assertEqual(owner, accounting.MUL)

    def test_qe_product_bank_splits_exponent_add_from_multiply(self):
        assigned, _ = self.assign('''
module dp_top (a, b, e, y); input a,b; output e,y;
 dp_qe_product_bank_0 bank (.a(a), .b(b), .out_exponents(e), .out_products(y));
endmodule
module dp_qe_product_bank_0 (a,b,out_exponents,out_products);
 input a,b; output out_exponents,out_products;
 BUF exponent_add (.A(a), .Y(out_exponents));
 dp_mul_unsigned_4_4 multiply (.in_a(a), .in_b(b), .out_product(out_products));
endmodule
module dp_mul_unsigned_4_4 (in_a,in_b,out_product);
 input in_a,in_b; output out_product;
 BUF multiplication (.A(in_a), .Y(out_product));
endmodule
''', ['bank/exponent_add', 'bank/multiply/multiplication'])
        self.assertEqual(assigned['bank/exponent_add']['category'], accounting.EXP)
        self.assertEqual(assigned['bank/multiply/multiplication']['category'], accounting.MUL)

    def test_common_anchor_delta_and_signed_output_are_distinct(self):
        assigned, _ = self.assign('''
module dp_global_align_0 (a, out_anchor, out_leaves);
 input a; output out_anchor, out_leaves; wire shift_delta, magnitude;
 BUF select_anchor (.A(a), .Y(out_anchor));
 BUF compute_delta (.A(a), .Y(shift_delta));
 dp_bidir_shift_0 shift (.in_net(shift_delta), .in_magnitude(a), .out_magnitude(magnitude));
 BUF restore_sign (.A(magnitude), .Y(out_leaves));
endmodule
module dp_bidir_shift_0 (in_net, in_magnitude, out_magnitude);
 input in_net,in_magnitude; output out_magnitude;
 BUF shifter (.A(in_magnitude), .Y(out_magnitude));
endmodule
''', ['select_anchor', 'compute_delta', 'shift/shifter', 'restore_sign'],
            top='dp_global_align_0')
        expected = {'select_anchor': accounting.EXP, 'compute_delta': accounting.ALIGN,
                    'shift/shifter': accounting.ALIGN, 'restore_sign': accounting.ADD}
        self.assertEqual({name: row['category'] for name, row in assigned.items()}, expected)
        self.assertEqual(sum(row['area_um2'] for row in assigned.values()), 5.0)

    def test_group_abs_owned_by_alignment_not_scale_multiply(self):
        assigned, _ = self.assign('''
module dp_group_0 (a, coefficient, y);
 input a,coefficient; output y; wire absolute_sop, selected_coefficient;
 BUF absolute_value (.A(a), .Y(absolute_sop));
 BUF coefficient_mux (.A(coefficient), .Y(selected_coefficient));
 dp_scale_multiply_0 scale (.in_magnitude(absolute_sop),
     .in_coefficient(selected_coefficient), .out_magnitude(y));
endmodule
module dp_scale_multiply_0 (in_magnitude,in_coefficient,out_magnitude);
 input in_magnitude,in_coefficient; output out_magnitude;
 BUF multiply (.A(in_magnitude), .Y(out_magnitude));
endmodule
''', ['absolute_value', 'coefficient_mux', 'scale/multiply'], top='dp_group_0')
        self.assertEqual(assigned['absolute_value']['category'], accounting.ALIGN)
        self.assertEqual(assigned['coefficient_mux']['category'], accounting.MUL)
        self.assertEqual(assigned['scale/multiply']['category'], accounting.MUL)

    def test_shared_cone_is_counted_once_in_others(self):
        exponent_register = 'ff_s1_s2_anchor_ff_storage_out_q_reg_0_'
        product_register = 'ff_s1_s2_product_ff_storage_out_q_reg_0_'
        assigned, audit = self.assign(f'''
module dp_top (a, q1, q2); input a; output q1,q2; wire shared;
 BUF shared_gate (.A(a), .Y(shared));
 DFF {exponent_register} (.D(shared), .Q(q1));
 DFF {product_register} (.D(shared), .Q(q2));
endmodule
''', ['shared_gate', exponent_register, product_register],
            sequential=(exponent_register, product_register))
        self.assertEqual(assigned['shared_gate']['category'], accounting.OTHER)
        self.assertEqual(assigned[exponent_register]['category'], accounting.EXP)
        self.assertEqual(assigned[product_register]['category'], accounting.MUL)
        self.assertEqual(audit[0]['overlap_cells'], 1)
        self.assertEqual(sum(row['area_um2'] for row in assigned.values()), 3.75)

    def test_icg_is_control_even_inside_decode(self):
        assigned, _ = self.assign('''
module dp_top (a,y); input a; output y;
 dp_lane_unpack_0 decode (.a(a), .y(y));
endmodule
module dp_lane_unpack_0 (a,y); input a; output y;
 BUF clk_gate_payload (.A(a), .Y(y));
endmodule
''', ['decode/clk_gate_payload'])
        self.assertEqual(assigned['decode/clk_gate_payload']['category'], accounting.OTHER)
        self.assertEqual(assigned['decode/clk_gate_payload']['component'], 'icg')


class ReportIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.netlist = self.root / 'mapped.v'
        self.netlist.write_text('module dp_top(a,y); input a; output y; '
                                'BUF U1 (.A(a),.Y(y)); endmodule\n')
        self.audit = dict(status='PASS', top='dp_top', format='bf16', area_um2=2.0,
                          internal_mw=2.0, switching_mw=1.0, dynamic_mw=3.0,
                          static_mw=0.1, total_mw=3.1, dc_run='dc', export_id='rtl')
        self.point = dict(artifacts=dict(mapped_verilog=dict(path='mapped.v')))
        self.patch_root = patch.object(accounting, 'ROOT', self.root)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
        self.patch_check = patch.object(accounting, 'check_point', side_effect=self.accept_point)
        self.patch_check.start()
        self.addCleanup(self.patch_check.stop)
        self.points = {}

    def accept_point(self, path):
        return self.points[path.name]

    def report(self, name, mode='bf16', mapped='mapped.v'):
        report = self.root / name
        report.mkdir()
        audit = dict(self.audit, format=mode)
        point = dict(self.point, artifacts=dict(mapped_verilog=dict(path=mapped)))
        self.points[name] = point, audit
        (report / 'source.json').write_text(json.dumps(dict(point=name, audit=audit)))
        (report / 'manifest.json').write_text(json.dumps(dict(files_sha256={})))
        (report / 'leaf_area.tsv').write_text('cell\tsequential\tarea_um2\nU1\tfalse\t2.0\n')
        (report / 'lib_functions.tsv').write_text(LIBRARY)
        (report / 'all_cell_net_power.rpt').write_text(
            'Dynamic Power Units = 1mW\nLeakage Power Units = 1nW\n'
            'hierarchy 200 100 300 (100%) 10000000\n'
            'U1 2 1 3 (100%) 100000\n')
        return report

    def test_seven_rows_reconcile_without_hierarchy_double_count(self):
        report = self.report('point')
        output = self.root / 'output'
        accounting.summarize([report], output)
        with (output / 'seven_functions_area.csv').open() as stream:
            area = list(csv.DictReader(stream))
        with (output / 'seven_functions_power.csv').open() as stream:
            power = list(csv.DictReader(stream))
        self.assertEqual(len(area), 7)
        self.assertEqual(len(power), 7)
        self.assertEqual(sum(float(row['total_um2']) for row in area), 2.0)
        self.assertEqual(sum(float(row['dynamic_mw']) for row in power), 3.0)
        self.assertAlmostEqual(sum(float(row['leakage_mw']) for row in power), 0.1)

    def test_duplicate_top_precision_point_is_rejected(self):
        report = self.report('point')
        with self.assertRaises(ValueError):
            accounting.summarize([report, report], self.root / 'output')

    def test_same_cell_inventory_does_not_prove_same_netlist(self):
        second = self.root / 'different.v'
        second.write_text('module dp_top(a,y); input a; output y; '
                          "BUF U1 (.A(1'b0),.Y(y)); endmodule\n")
        first_report = self.report('first')
        second_report = self.report('second', mode='mxfp4', mapped=second.name)
        with self.assertRaises(ValueError):
            accounting.summarize([first_report, second_report], self.root / 'output')

    def test_duplicate_physical_cell_is_rejected(self):
        report = self.report('point')
        with (report / 'leaf_area.tsv').open('a') as stream:
            stream.write('U1\tfalse\t2.0\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate leaf area'):
            accounting.summarize([report], self.root / 'output')

    def test_decimal_rounding_bound_respects_exponent_sign_and_units(self):
        report = self.root / 'rounding.rpt'
        report.write_text('parent 99.9 99.9 199.8 (100%) 999\n'
                          'U1 1.200e-3 2.345e-4 1.434e-3 (83%) 6.78\n'
                          'U2 -1.20e-7 0.0000 -1.20e-7 (100%) 1.230e-3\n')
        bounds = accounting.displayed_rounding_bounds(report, {'U1', 'U2'})
        self.assertAlmostEqual(bounds['internal_mw'], 0.5e-6 + 0.5e-9, places=16)
        self.assertAlmostEqual(bounds['switching_mw'], 0.5e-7, places=16)
        self.assertAlmostEqual(bounds['leakage_mw'], (0.5e-2 + 0.5e-6) * 1e-6, places=16)
        self.assertAlmostEqual(bounds['dynamic_mw'], bounds['internal_mw'] + bounds['switching_mw'])
        self.assertAlmostEqual(bounds['total_mw'], bounds['dynamic_mw'] + bounds['leakage_mw'])

    def rounded_report(self, internal_error):
        report = self.report('rounded')
        (report / 'all_cell_net_power.rpt').write_text(
            'Dynamic Power Units = 1mW\nLeakage Power Units = 1nW\n'
            'U1 2.0000 1.0000 3.0000 (100%) 100000.0\n')
        point, audit = self.points[report.name]
        audit.update(internal_mw=2.0 + internal_error,
                     dynamic_mw=3.0 + internal_error,
                     total_mw=3.1 + internal_error)
        (report / 'source.json').write_text(json.dumps(dict(point=report.name, audit=audit)))
        return report

    def test_printed_rounding_loss_is_accepted_without_rescaling(self):
        report = self.rounded_report(0.00002)
        output = self.root / 'output'
        accounting.summarize([report], output)
        with (output / 'seven_functions_power.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(sum(float(row['dynamic_mw']) for row in rows), 3.0)
        self.assertNotEqual(sum(float(row['dynamic_mw']) for row in rows), 3.00002)

    def test_actual_loss_beyond_printed_rounding_bound_is_rejected(self):
        report = self.rounded_report(0.0002)
        with self.assertRaisesRegex(ValueError, 'internal_mw leaf sum mismatch'):
            accounting.summarize([report], self.root / 'output')


if __name__ == '__main__':
    unittest.main()
