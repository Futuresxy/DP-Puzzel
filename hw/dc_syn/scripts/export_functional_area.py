#!/usr/bin/env python3
"""Read accepted DDC leaf areas/functions for local functional attribution.

No compile, SAIF, or power analysis. Commercial library functions stay local.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from run_dc import ROOT, run_path, verify_inputs, tcl_string


def export(run_id):
    run = run_path(run_id)
    data = verify_inputs(run)
    summary = json.loads((run/'summary.json').read_text())
    if not summary['flow_pass'] or summary['top'] != 'dp_top':
        raise ValueError('Requires accepted dp_top run')
    dest = run/'analysis'/('functional_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    dest.mkdir(parents=True, exist_ok=False)
    ddc = run/'netlist/dp_top.ddc'
    netlist = run/'netlist/dp_top_mapped.v'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {p.name:digest(p) for p in (ddc,netlist)}
    script = '''if {[catch {
source RESOLVED
set_svf -off
set target_library $target_dbs
set link_library [concat [list *] $target_dbs]
read_ddc DDC
current_design dp_top
if {![link]} {error "DDC link failed"}
set_app_var report_default_significant_digits 13
report_area -hierarchy -nosplit > area_hierarchy.rpt
set leaves [get_cells -hierarchical -filter {is_hierarchical == false}]
set f [open leaf_area.tsv w]
puts $f "cell\\tsequential\\treference\\tarea_um2"
set refs {}
foreach_in_collection c $leaves {
 puts $f "[get_object_name $c]\\t[get_attribute $c is_sequential]\\t[get_attribute $c ref_name]\\t[get_attribute $c area]"
 if {![get_attribute $c is_sequential]} {dict set refs [get_attribute $c ref_name] 1}
}
close $f
set f [open lib_functions.tsv w]
puts $f "reference\\tpin\\tdirection\\tfunction"
dict for {ref dummy} $refs {
 foreach_in_collection p [get_lib_pins -of_objects [get_lib_cells */$ref]] {
  puts $f "$ref\\t[lindex [split [get_object_name $p] /] end]\\t[get_attribute $p direction]\\t[get_attribute -quiet $p function]"
 }
}
close $f
puts FUNCTIONAL_AREA_EXPORT_PASS
} err]} {puts stderr "FUNCTIONAL_AREA_EXPORT_FAILED: $err"; exit 2}
exit 0
'''.replace('RESOLVED',tcl_string(run/'inputs/resolved.tcl')).replace('DDC\n',tcl_string(ddc)+'\n')
    (dest/'export.tcl').write_text(script)
    binding = data['machine']
    shell = 'set -e; if [[ -n "$1" ]]; then source "$1"; fi; cd "$2"; exec "$3" -no_home_init -no_local_init -f export.tcl'
    with (dest/'stdout.log').open('wb') as out, (dest/'stderr.log').open('wb') as err:
        proc = subprocess.run(['bash','-c',shell,'functional-area',binding['setup_script'],str(dest),binding['dc_shell']],stdout=out,stderr=err)
    log = (dest/'stdout.log').read_text()+(dest/'stderr.log').read_text()
    if proc.returncode or 'FUNCTIONAL_AREA_EXPORT_PASS\n' not in log or re.search(r'^\s*(Error:|Fatal:|FUNCTIONAL_AREA_EXPORT_FAILED:)',log,re.M):
        raise ValueError('Export failed; see '+str(dest))
    if before != {p.name:digest(p) for p in (ddc,netlist)}:
        raise ValueError('Accepted artifact changed')
    manifest = dict(status='PASS',source_run=run_id,export_id=summary['export_id'],no_compile=True,no_power=True,
                    source_hashes=before,files_sha256={n:digest(dest/n) for n in ('leaf_area.tsv','lib_functions.tsv','area_hierarchy.rpt')})
    (dest/'source.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(dest.relative_to(ROOT))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    export(parser.parse_args().run_id)
