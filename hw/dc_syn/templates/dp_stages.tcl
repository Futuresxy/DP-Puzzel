# DP v1.4 register ownership from src/spec/dp/dptop/pipeline.md and the unchanged RTL.
# Classification is reporting only: no path exceptions or optimization constraints.
proc dp_stage {name} {
  if {[regexp {operand_unpack_[ab]/} $name]} {return S1}
  if {[regexp {valid_q_reg(?:\[|_)([0-7])(?:\]|_)} $name -> index]} {return S[expr {$index+1}]}
  if {[regexp {(type_s|anchor_s|special_s|all_negative_s)([1-7])_q} $name -> stem stage]} {return S$stage}
  if {[regexp {lane/} $name]} {
    if {[regexp {/(products|exponents|negative|active)_q_reg} $name]} {return S2}
    if {[regexp {/leaves_q_reg} $name]} {return S3}
    if {[regexp {/out_(sop|anchor|all_negative)_reg} $name]} {return S4}
  } elseif {[regexp {group_unit/} $name]} {
    if {[regexp {/(sa|sb|ea|eb|nan_s1)_q_reg} $name]} {return S1}
    if {[regexp {/(type|coeff|scale_exp|scale_nan)_q_reg(?:\[|_)([0-3])(?:\]|_)} $name -> stem index]} {return S[expr {$index+1}]}
    if {[regexp {/(out_.*|special_q)_reg} $name]} {return S5}
  } else {
    if {[regexp {^(last|c_type|c_raw)_q_reg(?:\[|_)([0-7])(?:\]|_)} $name -> stem index]} {return S[expr {$index+1}]}
    if {[regexp {^c_(negative|magnitude|anchor|z|special)_q_reg} $name]} {return S5}
    if {[regexp {^leaves_q_reg|_s6_q_reg} $name]} {return S6}
    if {[regexp {^sum_q_reg|_s7_q_reg} $name]} {return S7}
    if {[regexp {^out_d_reg} $name]} {return S8}
  }
  return unclassified
}
proc report_dp_stages {} {
  array set stages {}
  set f [open reports/register_stages.tsv w]
  puts $f "register\tcapture_stage"
  foreach_in_collection reg [all_registers -data_pins] {
    set name [get_object_name [get_cells -of_objects $reg]]
    set stage [dp_stage $name]
    puts $f "$name\t$stage"
    if {![info exists stages($stage)]} {set stages($stage) [get_cells -quiet __dp_empty_collection__]}
    set stages($stage) [add_to_collection $stages($stage) $reg]
  }
  close $f
  set endpoints [open reports/endpoint_slacks.tsv w]
  puts $endpoints "stage\tstartpoint\tendpoint\tslack_ns"
  foreach stage [lsort [array names stages]] {
    redirect -file reports/timing_${stage}.rpt {
      report_timing -to $stages($stage) -delay_type max -max_paths 10 -significant_digits 9
    }
    foreach_in_collection path [get_timing_paths -to $stages($stage) -delay_type max -nworst 1 -max_paths 100000] {
      puts $endpoints "$stage\t[get_object_name [get_attribute $path startpoint]]\t[get_object_name [get_attribute $path endpoint]]\t[get_attribute $path slack]"
    }
  }
  close $endpoints
  redirect -file reports/timing_outputs.rpt {
    report_timing -to [all_outputs] -delay_type max -max_paths 10 -significant_digits 9
  }
}
