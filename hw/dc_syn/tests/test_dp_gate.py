"""Negative DP evidence tests; these fixtures do not claim RTL or EDA validation."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from dp_rtl_gate import payload, verify_dp_export, validate_scopes
spec=importlib.util.spec_from_file_location('dp_snapshot',ROOT/'test/adapters/rtl.py')
adapter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class DPGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        shutil.copytree(ROOT/'src/verilog',self.root/'src/verilog')
        with patch.object(adapter,'ROOT',self.root):
            self.export,_=adapter.snapshot('verilog')

    def test_unverified_snapshot_cannot_start_dc(self):
        payload(self.export,self.root)
        with self.assertRaisesRegex(ValueError,'no backend-eligible'):
            verify_dp_export(self.export.name,self.root)

    def test_editing_eligibility_flag_does_not_pass(self):
        p=self.export/'manifest.json'; m=json.loads(p.read_text())
        m.update(status='passed',ppa_eligible=True)
        p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            verify_dp_export(self.export.name,self.root)

    def test_source_and_snapshot_drift_are_rejected(self):
        p=self.export/'src/src/verilog/top/dp_top.v'
        p.write_text(p.read_text()+'\n// modified\n')
        with self.assertRaisesRegex(ValueError,'Modified DP snapshot'):
            payload(self.export,self.root)

    def test_reset_contract_is_explicit(self):
        path=self.export/'manifest.json'
        original=json.loads(path.read_text())
        for interface in (None, dict(original['interface'], reset_port='reset', reset_active='high')):
            modified=dict(original)
            if interface is None:
                modified.pop('interface')
            else:
                modified['interface']=interface
            path.write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError, 'clock/reset contract'):
                payload(self.export,self.root)

    def test_filelist_injection_is_rejected(self):
        p=self.export/'files.f'; p.write_text(p.read_text()+'src/src/verilog/systemverilog/top/dp_top.sv\n')
        with self.assertRaisesRegex(ValueError,'files.f mismatch'):
            payload(self.export,self.root)

    def test_partial_campaign_cannot_enable_ppa(self):
        with self.assertRaisesRegex(ValueError,'Full DP campaign'):
            validate_scopes([],self.root,0,1)

    def test_e_identity_and_unverified_evidence_are_checked(self):
        with patch.object(adapter,'ROOT',self.root):
            export,_=adapter.snapshot('verilog','e')
        manifest,_,_=payload(export,self.root)
        self.assertEqual(manifest['top'],'dp_top_e')
        with self.assertRaisesRegex(ValueError,'no backend-eligible'):
            verify_dp_export(export.name,self.root)
        p=export/'manifest.json'; manifest['top']='dp_top'; p.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            payload(export,self.root)

    def test_partial_e_campaign_cannot_enable_ppa(self):
        with self.assertRaisesRegex(ValueError,'Full DP campaign'):
            validate_scopes([],self.root,0,1,'e')

    def test_mixed_identity_and_incomplete_campaign_rejected(self):
        for frontend in ('t8h16q32e96','t8h16q32e128','t8h16q64e128'):
            with patch.object(adapter,'ROOT',self.root):
                export,_=adapter.snapshot('verilog',frontend)
            manifest,_,_=payload(export,self.root)
            self.assertEqual(manifest['top'],'dp_top_'+frontend)
            with self.assertRaisesRegex(ValueError,'no backend-eligible'):
                verify_dp_export(export.name,self.root)
            with self.assertRaisesRegex(ValueError,'Full DP campaign'):
                validate_scopes([],self.root,0,1,frontend)

    def test_stage_classification_preserves_top_and_lane_distinction(self):
        script='source {'+str(ROOT/'hw/dc_syn/templates/dp_stages.tcl')+'}\n'
        cases={'g_group_0__group_unit/g_lane_0__lane/operand_unpack_a/mantissa_q_reg[0][1]':'S1',
               'g_group_0__group_unit/g_lane_0__lane/products_q_reg[0]':'S2',
               'g_group_0__group_unit/g_lane_0__lane/leaves_q_reg[0]':'S3',
               'g_group_0__group_unit/g_lane_0__lane/out_sop_reg[0]':'S4',
               'g_group_0__group_unit/out_z_reg[0]':'S5',
               'leaves_q_reg[0]':'S6','sum_q_reg[0]':'S7','out_d_reg[0]':'S8', 'c_type_q_reg_6_':'S7', 'g_group_0__group_unit/type_q_reg_3__2_':'S4',
               'g_group_0__group_unit/g_lane_0__lane/a_mantissa_s1_q_reg[0]':'S1',
               'g_group_0__group_unit/g_lane_0__lane/pairs_s2_q_reg[0]':'S2',
               'g_group_0__group_unit/g_lane_0__lane/sop_s3_q_reg[0]':'S3',
               'g_group_0__group_unit/magnitude_s4_q_reg[0]':'S4'}
        for stage in range(1,9):
            cases[f'g_group_0__u_group/ff_s{stage-1}_s{stage}_payload/u_storage/out_q_reg[0]']=f'S{stage}'
        for name,stage in cases.items():
            script+='if {[dp_stage {'+name+'}] ne "'+stage+'"} {error "wrong stage"}\n'
        result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True)
        self.assertEqual(result.stderr,'')


if __name__=='__main__': unittest.main()
