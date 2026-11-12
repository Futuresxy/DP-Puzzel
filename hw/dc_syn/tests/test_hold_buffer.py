"""Software-only repair admission/connectivity tests, never EDA or timing evidence."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'hw/dc_syn/scripts'))
import run_dc


class HoldBufferAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dc = Path(self.tmp.name)
        shutil.copytree(ROOT / 'hw/dc_syn/templates', self.dc / 'templates')
        (self.dc / 'runs/dc_Fixture_10240001').mkdir(parents=True)
        self.args = Namespace(design_rule_repair_from='dc_Fixture_10240001',
                              hold_repair_from=None, timing_repair_from=None,
                              resize_inverter=[], resize_register=[],
                              insert_hold_buffer=[['core/register/D', 'DFQD1Fixture', 'DELBD1Fixture']],
                              run_id='dc_Fixture_10240002', purpose='SOFTWARE FIXTURE ONLY')
        self.data = dict(gate=dict(top='Fixture', sources=[], include_dirs=[], parameters={}),
                         constraints=run_dc.constraint_defaults({}), target_dbs=[],
                         technology=dict(operating_library='base', operating_condition='fixture',
                                         wire_load_model='fixture', target_libraries=['base', 'lvt'],
                                         multi_vt=dict(base_library='base', lvt_library='lvt', max_lvt_percent=20)))

    def prepare(self):
        with patch.object(run_dc, 'DC', self.dc), patch.object(run_dc, 'verify_repair_source') as source:
            run_dc.prepare(self.args, self.data)
            return source

    def test_actions_are_reproducible_bound_to_settings_and_source_gate(self):
        source = self.prepare()
        source.assert_called_once_with(self.data)
        run = self.dc / 'runs' / self.args.run_id
        stored = json.loads((run / 'inputs/resolved.json').read_text())
        action = stored['design_rule_repair']['insert_hold_buffers'][0]
        tag = hashlib.sha256(b'core/register/D').hexdigest()[:16]
        self.assertEqual(action, dict(endpoint_pin='core/register/D', expected_ref='DFQD1Fixture',
                                    buffer_ref='DELBD1Fixture', instance_name='dp_hold_buffer_' + tag,
                                    net_name='dp_hold_net_' + tag))
        settings = (run / 'inputs/resolved.tcl').read_text()
        for value in action.values():
            self.assertIn(run_dc.tcl_string(value), settings)
        with patch.object(run_dc, 'DC', self.dc):
            self.assertEqual(settings, run_dc.render_tcl(stored))
            altered = copy.deepcopy(stored)
            altered['design_rule_repair']['insert_hold_buffers'][0]['buffer_ref'] = 'DELBD2Fixture'
            self.assertNotEqual(settings, run_dc.render_tcl(altered))
        self.assertEqual(stored['constraints'], self.data['constraints'])
        self.assertEqual(stored['gate'], self.data['gate'])

    def test_actions_require_design_rule_repair(self):
        self.args.design_rule_repair_from = None
        self.args.hold_repair_from = 'dc_Fixture_10240001'
        with self.assertRaisesRegex(ValueError, 'requires design-rule repair'):
            self.prepare()

    def test_rejects_unsafe_or_non_data_endpoint_and_refs(self):
        for row in (['core/*/D', 'DFQD1Fixture', 'DELBD1Fixture'],
                    ['core/register/CP', 'DFQD1Fixture', 'DELBD1Fixture'],
                    ['core/register/D', 'DFF1Fixture', 'DELBD1Fixture'],
                    ['core/register/D', 'DFQD1Fixture', 'base/DELBD1Fixture'],
                    ['core/register/D', 'DFQD1Fixture', 'DELBD1Fixture;exit']):
            with self.subTest(row=row):
                self.args.insert_hold_buffer = [row]
                with self.assertRaisesRegex(ValueError, 'exact mapped DFQD D pin'):
                    self.prepare()

    def test_rejects_duplicates_resize_conflict_and_missing_base_library(self):
        self.args.insert_hold_buffer *= 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.prepare()
        self.args.insert_hold_buffer = self.args.insert_hold_buffer[:1]
        self.args.resize_register = [['core/register', 'DFQD1Fixture', 'DFQD2Fixture']]
        with self.assertRaisesRegex(ValueError, 'resize and buffer'):
            self.prepare()
        self.args.resize_register = []
        self.data['technology']['multi_vt'] = None
        with self.assertRaisesRegex(ValueError, 'base-library binding'):
            self.prepare()


# Collection/model fixtures for executing the real Tcl validation procedure.
# This intentionally models fanout and library semantics, not DC STA behavior.
FIXTURE = r'''
set inserted 0
set protected 0
set endpoint core/register/D
set oldnet input_net
set buffer_name core/dp_hold_buffer_fixture
set newnet core/dp_hold_net_fixture
set library_ref base/DFQD1Fixture
set register_ref DFQD1Fixture
set seq 1
set buffer_seq 0
set buffer_function I
set bad_mutation 0
set duplicate_pin 0
set pin_missing 0
set name_collision 0
set net_collision 0
set missing_net 0
set extra_pin 0
set returned_name_wrong 0
set nets(input_net) {input_port core/register/D core/other/D}
proc sizeof_collection {items} {llength $items}
proc get_object_name {items} {return $items}
proc get_pins {args} {
  global endpoint inserted newnet duplicate_pin pin_missing
  set name [lindex $args end]
  if {$name eq $endpoint} {
    if {$pin_missing} {return {}}
    if {$duplicate_pin} {return [list $endpoint alias/D]}
    return [list $endpoint]
  }
  return [list $name]
}
proc get_cells {args} {
  global inserted buffer_name name_collision returned_name_wrong endpoint
  if {[lsearch -exact $args -of_objects] >= 0} {return [file dirname $endpoint]}
  set name [lindex $args end]
  if {$name eq $buffer_name && ($inserted || $name_collision)} {
    if {$returned_name_wrong} {return renamed_buffer}
    return [list $name]
  }
  return {}
}
proc get_lib_cells {args} {
  global library_ref
  if {[lsearch -exact $args -of_objects] >= 0} {return [list $library_ref]}
  return [list [lindex $args end]]
}
proc get_lib_pins {args} {
  global extra_pin
  set name [lindex $args end]
  if {$name eq {base/DFQD1Fixture/*}} {
    return {base/DFQD1Fixture/CP base/DFQD1Fixture/D base/DFQD1Fixture/Q}
  }
  if {$name eq {base/DELBD1Fixture/*}} {
    set pins {base/DELBD1Fixture/I base/DELBD1Fixture/Z}
    if {$extra_pin} {lappend pins base/DELBD1Fixture/EN}
    return $pins
  }
  return [list $name]
}
proc get_attribute {object key} {
  global register_ref seq buffer_seq buffer_function endpoint
  if {$key eq "ref_name"} {
    if {$object eq [file dirname $endpoint]} {return $register_ref}
    return DELBD1Fixture
  }
  if {$key eq "is_sequential"} {
    if {$object eq "base/DFQD1Fixture"} {return $seq}
    return $buffer_seq
  }
  if {$key eq "direction"} {
    if {[file tail $object] in {Q Z}} {return out}
    return in
  }
  if {$key eq "function"} {return $buffer_function}
  error "Unexpected fixture attribute: $object $key"
}
proc filter_collection {items filter} {
  set direction [lindex $filter 2]
  set result {}
  foreach object $items {
    if {[get_attribute $object direction] eq $direction} {lappend result $object}
  }
  return $result
}
proc get_nets {args} {
  global inserted newnet oldnet nets net_collision missing_net
  if {[lsearch -exact $args -of_objects] >= 0} {
    if {$missing_net} {return {}}
    if {$inserted} {return [list $newnet]}
    return [list $oldnet]
  }
  set name [lindex $args end]
  if {[info exists nets($name)] || ($name eq $newnet && $net_collision)} {return [list $name]}
  return {}
}
proc all_connected {net} {global nets; return $nets($net)}
proc insert_buffer {args} {
  global inserted endpoint oldnet buffer_name newnet nets bad_mutation
  if {$args ne [list -new_net_names [file tail $newnet] -new_cell_names [file tail $buffer_name] $endpoint base/DELBD1Fixture]} {
    error "Unexpected insert_buffer invocation: $args"
  }
  set inserted 1
  set nets($oldnet) [list input_port core/other/D ${buffer_name}/I]
  set nets($newnet) [list $endpoint ${buffer_name}/Z]
  if {$bad_mutation} {
    set nets($oldnet) [list input_port ${buffer_name}/I]
    lappend nets($newnet) core/other/D
  }
  return [list $buffer_name]
}
proc set_dont_touch {cell value} {
  global protected buffer_name
  if {$cell ne $buffer_name || !$value} {error "Wrong protected object"}
  set protected 1
}
'''


@unittest.skipUnless(shutil.which('tclsh'), 'Tcl not installed')
class HoldBufferTclTests(unittest.TestCase):
    def run_fixture(self, setup=''):
        template = (ROOT / 'hw/dc_syn/templates/DC.tcl').read_text()
        block = template.split('# BEGIN targeted hold buffer validation', 1)[1]
        block = block[block.index('proc dp_insert_hold_buffer'):]
        block = block.split('# END targeted hold buffer validation.', 1)[0]
        script = FIXTURE + '\n' + setup + '\n' + block + r'''
set rc [catch {dp_insert_hold_buffer [list $endpoint DFQD1Fixture DELBD1Fixture [file tail $buffer_name] [file tail $newnet]] base} message]
puts [list RESULT $rc $inserted $protected $message]
'''
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_preserves_other_fanout_and_protects_only_added_identity_buffer(self):
        result = self.run_fixture()
        self.assertIn('DP_HOLD_BUFFER_INSERT core/register/D DFQD1Fixture base/DELBD1Fixture', result)
        self.assertIn('RESULT 0 1 1', result)

    def test_top_level_endpoint_uses_leaf_names_without_dot_prefix(self):
        result = self.run_fixture("""
set endpoint register/D
set buffer_name dp_hold_buffer_fixture
set newnet dp_hold_net_fixture
set nets(input_net) [list input_port $endpoint core/other/D]
""")
        self.assertIn('RESULT 0 1 1', result)

    def test_preinsertion_rejections_do_not_mutate_design(self):
        for setting in ('set duplicate_pin 1', 'set pin_missing 1',
                        'set register_ref DFQD2Fixture', 'set library_ref lvt/DFQD1Fixture',
                        'set seq 0', 'set buffer_seq 1', 'set buffer_function !I',
                        'set buffer_function {I | EN}', 'set name_collision 1',
                        'set net_collision 1', 'set missing_net 1', 'set extra_pin 1'):
            with self.subTest(setting=setting):
                self.assertIn('RESULT 1 0 0', self.run_fixture(setting))

    def test_unexpected_non_target_load_move_fails_closed(self):
        result = self.run_fixture('set bad_mutation 1')
        self.assertIn('RESULT 1 1 0', result)
        self.assertIn('changed unexpected connectivity', result)

    def test_tool_name_substitution_is_rejected(self):
        result = self.run_fixture('set returned_name_wrong 1')
        self.assertIn('RESULT 1 1 0', result)
        self.assertIn('changed unexpected connectivity', result)


if __name__ == '__main__':
    unittest.main()
