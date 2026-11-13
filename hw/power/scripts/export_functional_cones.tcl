if {[catch {
 source $env(DP_POWER_CONFIG)
 set_svf -off
 set target_library $databases
 set link_library [concat [list *] $databases]
 read_ddc $ddc
 current_design $top
 if {![link]} {error "link failed"}
 set f [open lib_functions.tsv w]
 puts $f "reference\tpin\tdirection\tfunction"
 set refs {}
 foreach_in_collection c [get_cells -hierarchical -filter {is_hierarchical == false && is_sequential == false}] {
  dict set refs [get_attribute $c ref_name] 1
 }
 dict for {ref dummy} $refs {
  set lc [get_lib_cells */$ref]
  foreach_in_collection p [get_lib_pins -of_objects $lc] {
   set pn [lindex [split [get_object_name $p] /] end]
   set fn [get_attribute -quiet $p function]
   puts $f "$ref\t$pn\t[get_attribute $p direction]\t$fn"
  }
 }
 close $f
 set f [open retained_arithmetic_nets.txt w]
 foreach_in_collection n [get_nets -hierarchical -filter {full_name =~ *pair* || full_name =~ *absolute_sop* || full_name =~ *anchor_work*}] {
  puts $f [get_object_name $n]
 }
 close $f
 puts FUNCTION_EXPORT_PASS
} message]} {puts stderr $message;exit 2}
exit
