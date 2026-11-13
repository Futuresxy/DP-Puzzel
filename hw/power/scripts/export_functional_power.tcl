# Read-only reporting from an accepted DDC and its audited workload SAIF.
# Run in a new report directory; DP_POWER_CONFIG points to the original config.tcl.
if {[catch {
  source $env(DP_POWER_CONFIG)
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
  set_annotated_transition $clock_slew_ns $clock_objects
  report_area -nosplit > area.rpt
  report_power -analysis_effort high > power.rpt
  # Move register clock-pin internal power back into cell accounting; do not add
  # clock_network again. Each cell row includes switching on its driven nets.
  set_app_var power_clock_network_include_register_clock_pin_power false
  report_power -analysis_effort high > power_cell_accounting.rpt
  report_power -cell -net -flat -nosplit -sort_mode name -analysis_effort high > all_cell_net_power.rpt
  set fh [open leaf_area.tsv w]
  puts $fh "cell\tsequential\treference\tarea_um2"
  foreach_in_collection cell $leaves {
    puts $fh "[get_object_name $cell]\t[get_attribute $cell is_sequential]\t[get_attribute $cell ref_name]\t[get_attribute $cell area]"
  }
  close $fh
  redirect -file cell_attributes.rpt {list_attributes -application -class cell}
  redirect -file report_power.man {man report_power}
  puts DP_FUNCTIONAL_REPORT_PASS
} message]} {
  puts stderr "DP_FUNCTIONAL_REPORT_FAILED: $message"
  exit 2
}
exit
