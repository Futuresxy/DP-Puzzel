# Pure selection rules are also exercised with Tcl outside DC.
proc matches_any {value patterns} {
  foreach pattern $patterns { if {[string match $pattern $value]} { return 1 } }
  return 0
}

proc hierarchy_plan {rows keep_modules expand_modules expand_instances expand_depth} {
  set protected {}
  foreach row $rows {
    lassign $row path reference
    if {[matches_any $reference $keep_modules]} { lappend protected $path }
  }
  set result {}
  foreach row $rows {
    lassign $row path reference
    set depth [llength [split $path /]]
    set protect 0
    foreach prefix $protected {
      if {$path eq $prefix || [string first "$prefix/" $path] == 0} { set protect 1 }
    }
    set expand [expr {($expand_depth > 0 && $depth <= $expand_depth) ||
      [matches_any $reference $expand_modules] || [matches_any $path $expand_instances]}]
    set action keep
    if {$protect} { set action keep_pe } elseif {$expand} { set action expand }
    lappend result [list $path $reference $depth $action]
  }
  return $result
}

proc deepest_first {left right} {
  set difference [expr {[lindex $right 2] - [lindex $left 2]}]
  if {$difference != 0} { return $difference }
  return [string compare [lindex $left 0] [lindex $right 0]]
}
