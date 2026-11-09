"""Archived reuse requires DC's receipt and any additional receipt a point names.

This deliberately changes only latest validation metadata while preserving a
frozen source. Numerical-scope validation and DC report analysis have independent
test suites; their interfaces are mocked here to isolate receipt binding.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import dp_power_gate as gate


class ArchivedReceiptTests(unittest.TestCase):
    ORIGINAL_ID = '20261109T010203123456Z'
    LATER_ID = '20261109T020304123456Z'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source_name = 'src/verilog/top/dp_top.v'
        source = b'module dp_top(input clock, input rst_n); endmodule\n'
        source_hashes = {source_name: hashlib.sha256(source).hexdigest()}
        source_fingerprint = hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest()
        self.export_id = 'DP_verilog_' + source_fingerprint[:16]
        self.export = self.root / 'hw/rtl' / self.export_id
        payload = self.export / 'src' / source_name
        payload.parent.mkdir(parents=True)
        payload.write_bytes(('// RTL_ID: ' + self.export_id + '\n').encode() + source)
        (self.export / 'files.f').write_text('+incdir+src/src/verilog/parameter\nsrc/' + source_name + '\n')
        self.fingerprint = gate.rtl_fingerprint(self.export)
        self.manifest = dict(top='dp_top', frontend='multi', interface=gate.DP_INTERFACE,
                             rtl_fingerprint=self.fingerprint, source_sha256=source_hashes,
                             source_fingerprint=source_fingerprint, status='generated',
                             ppa_eligible=False, verification_id=self.LATER_ID)
        self.write(self.export / 'manifest.json', self.manifest)
        self.receipt = dict(verification_id=self.ORIGINAL_ID, export_id=self.export_id,
                            rtl_fingerprint=self.fingerprint, status='passed',
                            method='verilog_testbench', numerical_pass=True, protocol_pass=True,
                            parameters=gate.PARAMETERS, phase='all', latency=8, ii=1,
                            frontend='multi', seeds=[20271105], command=['verilator', '--binary'],
                            simulator=dict(name='verilator', version='test-version'),
                            scopes=[dict(export_id=self.export_id, name='original-complete-campaign')],
                            started_utc='2026-11-09T01:00:00+00:00',
                            finished_utc='2026-11-09T01:01:00+00:00')
        self.original_path = self.receipt_path(self.ORIGINAL_ID)
        self.write(self.original_path, self.receipt)
        self.later_receipt = dict(self.receipt, verification_id=self.LATER_ID,
                                  status='failed', numerical_pass=False,
                                  scopes=[dict(export_id=self.export_id, name='later-complete-campaign')],
                                  started_utc='2026-11-09T02:00:00+00:00',
                                  finished_utc='2026-11-09T02:01:00+00:00')
        self.write(self.receipt_path(self.LATER_ID), self.later_receipt)
        self.run = self.root / 'hw/dc_syn/runs/original'
        self.resolved = dict(gate=dict(verification_id=self.ORIGINAL_ID,
                                      rtl_fingerprint=self.fingerprint, export_id=self.export_id,
                                      top='dp_top', parameters=gate.PARAMETERS))
        self.write(self.run / 'inputs/resolved.json', self.resolved)
        netlist = self.run / 'outputs/mapped.v'
        netlist.parent.mkdir(parents=True)
        netlist.write_text('module dp_top; endmodule\n')
        self.point = dict(top='dp_top', export_id=self.export_id,
                          original_verification_id=self.ORIGINAL_ID,
                          dc_run=str(self.run.relative_to(self.root)),
                          artifacts=dict(mapped_verilog=dict(path=str(netlist.relative_to(self.root)),
                                                             sha256=gate.digest(netlist))))
        self.scope_validator = Mock()
        self.scope_patch = patch.object(gate, 'validate_scopes', self.scope_validator)
        self.scope_patch.start()
        self.addCleanup(self.scope_patch.stop)
        self.report_analyzer = Mock(return_value=dict(flow_pass=True))
        self.repair_validator = Mock()
        self.module_patch = patch.dict(sys.modules, {
            'report_dc': SimpleNamespace(analyze=self.report_analyzer),
            'run_dc': SimpleNamespace(verify_repair_source=self.repair_validator),
        })
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        previous_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), previous_path))

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def receipt_path(self, verification_id):
        return self.root / 'test/runs/verilog' / verification_id / 'verification.json'

    def verify(self):
        return gate.frozen_dc_source(self.root, self.point)

    def enable_additional_receipt(self):
        self.later_receipt.update(status='passed', numerical_pass=True)
        self.write(self.receipt_path(self.LATER_ID), self.later_receipt)
        self.point['original_verification_id'] = self.LATER_ID

    def test_latest_generated_manifest_does_not_replace_original_acceptance(self):
        result = self.verify()
        self.assertEqual(result['original_receipt_sha256'], gate.digest(self.original_path))
        self.assertNotEqual(result['original_receipt_sha256'], gate.digest(self.receipt_path(self.LATER_ID)))
        self.assertEqual(result['scope'], 'archived_dc_reuse_only')
        self.scope_validator.assert_called_once_with(
            self.receipt['scopes'], self.root,
            datetime.fromisoformat(self.receipt['started_utc']).timestamp(),
            datetime.fromisoformat(self.receipt['finished_utc']).timestamp(), 'multi')
        self.report_analyzer.assert_called_once_with(self.run, self.resolved)
        self.repair_validator.assert_called_once_with(self.resolved)

    def test_additional_passed_receipt_preserves_dc_original_binding(self):
        self.enable_additional_receipt()
        result = self.verify()
        self.assertEqual(result['original_receipt_sha256'], gate.digest(self.original_path))
        self.assertEqual(result['additional_verification_id'], self.LATER_ID)
        self.assertEqual(result['additional_receipt_sha256'], gate.digest(self.receipt_path(self.LATER_ID)))
        self.assertEqual(self.scope_validator.call_count, 2)
        self.scope_validator.assert_any_call(
            self.receipt['scopes'], self.root,
            datetime.fromisoformat(self.receipt['started_utc']).timestamp(),
            datetime.fromisoformat(self.receipt['finished_utc']).timestamp(), 'multi')
        self.scope_validator.assert_any_call(
            self.later_receipt['scopes'], self.root,
            datetime.fromisoformat(self.later_receipt['started_utc']).timestamp(),
            datetime.fromisoformat(self.later_receipt['finished_utc']).timestamp(), 'multi')

    def test_failed_original_cannot_fall_back_to_latest_pass(self):
        self.enable_additional_receipt()
        self.write(self.original_path, dict(self.receipt, numerical_pass=False))
        with self.assertRaises(ValueError):
            self.verify()

    def test_failed_additional_is_not_ignored_when_original_passes(self):
        self.point['original_verification_id'] = self.LATER_ID
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_original_cannot_be_replaced_by_additional(self):
        self.enable_additional_receipt()
        self.original_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.verify()

    def test_additional_payload_or_frontend_mismatch_is_rejected(self):
        self.enable_additional_receipt()
        for replacement in (dict(export_id='DP_verilog_other'),
                            dict(frontend='e64'), dict(rtl_fingerprint='0' * 64),
                            dict(parameters=dict(K_FP16=8, LOCAL_W=28, GLOBAL_W=40))):
            with self.subTest(replacement=replacement):
                self.write(self.receipt_path(self.LATER_ID), dict(self.later_receipt, **replacement))
                with self.assertRaises(ValueError):
                    self.verify()

    def test_additional_scope_failure_is_not_ignored(self):
        self.enable_additional_receipt()
        self.scope_validator.side_effect = [None, ValueError('Additional scope evidence changed')]
        with self.assertRaisesRegex(ValueError, 'Additional scope evidence changed'):
            self.verify()
        self.report_analyzer.assert_not_called()

    def test_additional_scope_cannot_reference_another_export(self):
        self.enable_additional_receipt()
        receipt = deepcopy(self.later_receipt)
        receipt['scopes'][0]['export_id'] = 'DP_verilog_different'
        self.write(self.receipt_path(self.LATER_ID), receipt)
        with self.assertRaises(ValueError):
            self.verify()

    def test_each_receipt_rejects_reversed_start_and_finish(self):
        self.enable_additional_receipt()
        for verification_id, receipt in ((self.ORIGINAL_ID, self.receipt),
                                         (self.LATER_ID, self.later_receipt)):
            with self.subTest(verification_id=verification_id):
                self.write(self.receipt_path(verification_id), dict(
                    receipt, started_utc=receipt['finished_utc'],
                    finished_utc=receipt['started_utc']))
                with self.assertRaises(ValueError):
                    self.verify()
                self.write(self.receipt_path(verification_id), receipt)

    def test_additional_completed_before_original_is_rejected(self):
        self.enable_additional_receipt()
        self.write(self.receipt_path(self.LATER_ID), dict(
            self.later_receipt, started_utc='2026-11-09T00:58:00+00:00',
            finished_utc='2026-11-09T00:59:00+00:00'))
        with self.assertRaisesRegex(ValueError, 'predates original DC acceptance'):
            self.verify()

    def test_overlapping_additional_campaign_with_later_finish_is_allowed(self):
        self.enable_additional_receipt()
        self.write(self.receipt_path(self.LATER_ID), dict(
            self.later_receipt, started_utc='2026-11-09T00:59:00+00:00',
            finished_utc='2026-11-09T01:02:00+00:00'))
        result = self.verify()
        self.assertEqual(result['original_receipt_sha256'], gate.digest(self.original_path))
        self.assertEqual(result['additional_verification_id'], self.LATER_ID)
        self.assertEqual(self.scope_validator.call_count, 2)

    def test_empty_additional_id_cannot_fall_back_to_original(self):
        for invalid_id in ('', None, False, 0):
            with self.subTest(invalid_id=invalid_id):
                self.point['original_verification_id'] = invalid_id
                with self.assertRaises(ValueError):
                    self.verify()

    def test_original_scope_failure_is_not_ignored(self):
        self.scope_validator.side_effect = ValueError('Original scope evidence changed')
        with self.assertRaisesRegex(ValueError, 'Original scope evidence changed'):
            self.verify()
        self.report_analyzer.assert_not_called()

    def test_receipt_for_different_frontend_or_fingerprint_is_rejected(self):
        for replacement in (dict(frontend='e64'), dict(rtl_fingerprint='0' * 64)):
            with self.subTest(replacement=replacement):
                self.write(self.original_path, dict(self.receipt, **replacement))
                with self.assertRaises(ValueError):
                    self.verify()

    def test_original_scope_cannot_reference_another_export(self):
        receipt = deepcopy(self.receipt)
        receipt['scopes'][0]['export_id'] = 'DP_verilog_different'
        self.write(self.original_path, receipt)
        with self.assertRaises(ValueError):
            self.verify()

    def test_changed_derived_netlist_is_rejected(self):
        path = self.root / self.point['artifacts']['mapped_verilog']['path']
        path.write_text(path.read_text() + '// changed\n')
        with self.assertRaisesRegex(ValueError, 'Mapped artifact changed'):
            self.verify()

    def test_failed_dc_is_still_rejected(self):
        self.report_analyzer.return_value = dict(flow_pass=False)
        with self.assertRaisesRegex(ValueError, 'Original DC result is not passing'):
            self.verify()

    def test_receipt_id_rejects_path_traversal(self):
        self.point['original_verification_id'] = '../' + self.ORIGINAL_ID
        with self.assertRaises(ValueError):
            self.verify()


if __name__ == '__main__':
    unittest.main()
