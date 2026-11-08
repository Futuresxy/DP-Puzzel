"""Negative controls for archived workload receipts and power evidence parsers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import dp_power_gate

spec = importlib.util.spec_from_file_location('dp_run_power', ROOT / 'hw/power/scripts/run_power.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.dependencies()
from power_report import parse_power
from saif_activity import audit_saif


class ReplayGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.point = dict(export_id='frozen', top='dp_top', format='bf16', logical_k=16)
        (self.root / 'log').write_text('POWER_SIM_PASS accepted=1025 checked=1025 workload=1024 latency=8\n')
        (self.root / 'expected').write_text('3f800000 0 0\n' * 1025)
        (self.root / 'results').write_text(''.join(f'{i} 3f800000 0 0\n' for i in range(1025)))
        self.receipt = dict(self.point, status='passed', method='verilog_testbench', rtl_fingerprint='hash',
                            latency=8, ii=1, simulator_version='test', commands=['test'],
                            total_transactions=1025, workload_transactions=1024,
                            simulation_log='log', expected_file='expected', results_file='results')
        self.rehash()
        gate = patch.object(dp_power_gate, 'frozen_dc_source', return_value={'rtl_fingerprint': 'hash'})
        gate.start()
        self.addCleanup(gate.stop)

    def rehash(self):
        self.receipt['files_sha256'] = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                                        for name in ('log', 'expected', 'results')}

    def verify(self):
        path = self.root / 'receipt.json'
        path.write_text(json.dumps(self.receipt))
        return dp_power_gate.verify_workload_replay(self.root, self.point, path)

    def test_complete_replay(self):
        self.verify()

    def test_changed_result(self):
        (self.root / 'results').write_text('changed')
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_result_even_when_rehashed(self):
        path = self.root / 'results'
        path.write_text(path.read_text().replace('3f800000', '3f800001', 1))
        self.rehash()
        with self.assertRaises(ValueError):
            self.verify()

    def test_unhashed_evidence(self):
        del self.receipt['files_sha256']['log']
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_export(self):
        self.receipt['export_id'] = 'another_export'
        with self.assertRaises(ValueError):
            self.verify()

    def test_short_workload(self):
        self.receipt['workload_transactions'] = 1023
        with self.assertRaises(ValueError):
            self.verify()


class ActivityTest(unittest.TestCase):
    def test_mixed_report_units(self):
        result = parse_power('Total 1 mW 2 mW 100000 nW 3.1 mW\n')
        self.assertAlmostEqual(result['leakage'], 0.0001)
        self.assertAlmostEqual(result['total'], 0.0031)

    def test_inconsistent_report(self):
        with self.assertRaises(ValueError):
            parse_power('Total 1 mW 2 mW 100000 nW 5 mW\n')

    def test_real_pin_x_and_duration_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.saif'
            def write(unknown):
                path.write_text('(SAIFILE (SAIFVERSION "2.0") (TIMESCALE 1 fs) (DURATION 10) '
                                '(INSTANCE dut (NET (clock (T0 5) (T1 ' + str(5-unknown) + ') '
                                '(TX ' + str(unknown) + ') (TZ 0) (TC 2)))))\n')
            write(0)
            audit_saif(path, {'dut': ['clock']}, 10, 'dut')
            with self.assertRaises(ValueError):
                audit_saif(path, {'dut': ['clock']}, 20, 'dut')
            write(1)
            with self.assertRaises(ValueError):
                audit_saif(path, {'dut': ['clock']}, 10, 'dut')


if __name__ == '__main__':
    unittest.main()
