# DP adaptation of Quant_LLM_Chip_Codesign native_power.tcl; see ../NOTICE.md.
# Restore original mapped DDC. No compile, retiming, or activity propagation fallback.
if {[catch {
  source config.tcl
  set_svf -off
  set target_library $databases
  set link_library [concat [list *] $databases]
  read_ddc $ddc
  current_design $top
  if {![link]} {error "Cannot link original DDC"}
  set_app_var report_default_significant_digits 13
  reset_switching_activity
  read_saif -input $saif_file -instance_name $scope -unit_base ns -verbose
  report_saif -hierarchy > activity.rpt
  report_saif -missing > activity_missing.rpt
  set leaves [get_cells -hierarchical -filter {is_hierarchical == false}]
  set leaf_pins [get_pins -of_objects $leaves]
  set clock_pins [all_registers -clock_pins]
  set extra [filter_collection $leaf_pins {is_clock_gate_output_pin == true || is_clock_used_as_clock == true}]
  set clock_pins [add_to_collection -unique $clock_pins $extra]
  set clocks [get_clocks $clock_name]
  if {[sizeof_collection $clocks] != 1} {error "Expected one restored clock"}
  set_clock_transition $clock_slew_ns $clocks
  set clock_objects [add_to_collection -unique $clock_pins [get_ports $clock_name]]
  if {[sizeof_collection [filter_collection $clock_pins {is_clock_gate_enable_pin == true || is_clock_gate_test_pin == true}]]} {
    error "Clock selection contains enable/test pins"
  }
  set_annotated_transition $clock_slew_ns $clock_objects
  report_annotated_transition -nosplit > clock_transitions.rpt
  report_timing -max_paths 1 > timing.rpt
  report_power -analysis_effort high > power.rpt
  report_power -analysis_effort high -hierarchy -levels 8 -nosplit > hierarchy_power.rpt
  redirect -file pin_activity.rpt {get_switching_activity -significant_digits 13 $leaf_pins}
  redirect -file clock_activity.rpt {get_switching_activity -significant_digits 13 $clock_objects}
  puts DP_POWER_COMPILER_PASS
} message]} {
  puts stderr "DP_POWER_COMPILER_FAILED: $message"
  exit 2
}
exit
