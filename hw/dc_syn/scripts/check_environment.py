#!/usr/bin/env python3
"""Probe the configured DC license and exact libraries without reading any RTL."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from run_dc import ROOT, tcl_string


def probe(technology, machine):
    tech = json.loads(technology.read_text())
    binding = json.loads(machine.read_text())
    dest = ROOT/'.cache'/('dc-environment-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    dest.mkdir(parents=True)
    script = ['if {[catch {', 'set_svf -off']
    for lib in tech['target_libraries']:
        if not re.fullmatch(r'[A-Za-z0-9_]+',lib):
            raise ValueError('Invalid library identifier')
        path = Path(binding['libraries'][lib])
        if path.name != lib+'.db' or not path.is_file():
            raise ValueError('Missing selected library: '+lib)
        with path.open('rb') as stream:
            stream.read(1)
        script += ['read_db '+tcl_string(path),
                   'if {[sizeof_collection [get_libs -quiet '+lib+']] != 1} {error "Library identity mismatch"}',
                   'puts "DP_LIBRARY '+lib+' cells=[sizeof_collection [get_lib_cells '+lib+'/*]]"']
    script += ['puts "DP_ENVIRONMENT_PASSED"', '} err]} {puts stderr "DP_ENVIRONMENT_FAILED: $err"; exit 2}', 'exit 0']
    (dest/'probe.tcl').write_text('\n'.join(script)+'\n')
    shell = 'set -e; if [[ -n "$1" ]]; then source "$1"; fi; cd "$2"; exec "$3" -no_home_init -no_local_init -f probe.tcl'
    with (dest/'stdout.log').open('wb') as out, (dest/'stderr.log').open('wb') as err:
        proc = subprocess.run(['bash','-c',shell,'dc-probe',binding['setup_script'],str(dest),binding['dc_shell']],stdout=out,stderr=err)
    output = (dest/'stdout.log').read_text(errors='replace')+(dest/'stderr.log').read_text(errors='replace')
    ok = proc.returncode == 0 and 'DP_ENVIRONMENT_PASSED\n' in output and not re.search(r'^\s*(Error:|Fatal:|DP_ENVIRONMENT_FAILED:)',output,re.M)
    result = dict(status='passed' if ok else 'failed',exit_code=proc.returncode,
                  technology_id=tech['technology_id'],libraries=tech['target_libraries'],
                  purpose='License checkout and exact DB read; no RTL synthesis',logs=str(dest.relative_to(ROOT)))
    (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if ok else 2


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--technology',required=True,type=Path)
    ap.add_argument('--machine',required=True,type=Path)
    args=ap.parse_args()
    sys.exit(probe(args.technology,args.machine))
