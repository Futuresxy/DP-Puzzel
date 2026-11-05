#!/usr/bin/env python3
"""Read a completed DDC and report DP stages; never optimize or rewrite netlists."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from run_dc import ROOT, DC, run_path, verify_inputs, tcl_string, dump
from report_dc import critical_path, read


def inspect(run_id):
    run=run_path(run_id)
    data=verify_inputs(run)
    if json.loads((run/'state.json').read_text())['phase'] != 'finished':
        raise ValueError('Inspection requires completed synthesis')
    dest=run/'analysis'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    (dest/'reports').mkdir(parents=True)
    shutil.copyfile(DC/'templates/dp_stages.tcl',dest/'dp_stages.tcl')
    script='''if {[catch {
source RESOLVED
set_app_var target_library $target_dbs
set_app_var link_library [concat [list *] $target_dbs]
set_svf -off
read_ddc NETLIST
current_design $top
if {![link]} {error "DDC link failed"}
source dp_stages.tcl
report_dp_stages
report_timing -delay_type max -max_paths 50 -significant_digits 9 > reports/timing_setup.rpt
report_qor -significant_digits 9 > reports/qor.rpt
puts "DP_INSPECTION_COMPLETE"
} err]} {puts stderr "DP_INSPECTION_FAILED: $err"; exit 2}
exit 0
'''.replace('RESOLVED',tcl_string(run/'inputs/resolved.tcl')).replace('NETLIST',tcl_string(run/'netlist'/ (data['gate']['top']+'.ddc')))
    (dest/'inspect.tcl').write_text(script)
    binding=data['machine']
    shell='set -e; if [[ -n "$1" ]]; then source "$1"; fi; cd "$2"; exec "$3" -no_home_init -no_local_init -f inspect.tcl'
    with (dest/'stdout.log').open('wb') as out, (dest/'stderr.log').open('wb') as err:
        proc=subprocess.run(['bash','-c',shell,'dc-inspect',binding['setup_script'],str(dest),binding['dc_shell']],stdout=out,stderr=err)
    texts=read(dest/'stdout.log')+read(dest/'stderr.log')+'\n'.join(read(p) for p in (dest/'reports').glob('*.rpt'))
    if proc.returncode or 'DP_INSPECTION_COMPLETE\n' not in texts or re.search(r'^\s*(Error:|Fatal:|DP_INSPECTION_FAILED:)',texts,re.M):
        raise ValueError('DDC inspection failed; see '+str(dest))
    original=critical_path(read(run/'reports/timing_setup.rpt'))
    restored=critical_path(read(dest/'reports/timing_setup.rpt'))
    if original != restored:
        raise ValueError('Reloaded DDC timing differs; inspection is not accepted: '+str(restored))
    stages={p.stem[7:]:critical_path(read(p)) for p in sorted((dest/'reports').glob('timing_S*.rpt'))}
    if len(stages)!=8 or any(v['slack_ns'] is None for v in stages.values()):
        raise ValueError('Incomplete stage timing reports')
    result=dict(status='passed',source_run=run_id,analysis_dir=str(dest.relative_to(run)),
                method='read saved DDC; no optimization; global critical path reproduced exactly',
                stage_setup_paths=stages,critical_setup_path=restored)
    dump(dest/'result.json',result)
    dump(run/'stage_analysis.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run-id',required=True)
    inspect(ap.parse_args().run_id)
