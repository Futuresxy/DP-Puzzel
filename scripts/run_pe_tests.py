#!/usr/bin/env python3
"""Run the six fixed PE testbenches against shared format/K logical TXT vectors."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hw/test/flow'))
from pe_vectors import ROOT,DATA_ROOT,FORMATS,PROFILES,DEFAULT_DATASETS,native_k,validate_case
sys.path.insert(0,str(ROOT/'hw/test/reference'))
from fp32_compare import compare_files,compare_segments,compare_random_case


def inspect_export(export_id,profile):
 if Path(export_id).name!=export_id:raise ValueError('explicit export ID required')
 d=ROOT/'hw/rtl'/export_id;m=json.loads((d/'manifest.json').read_text())
 kind,base,mids=PROFILES[profile]
 expected=[f'PE_{family}_g{words//4}' for family,words in mids]
 if (m['schema_version']!=2 or m['rtl_id']!=export_id or m['state']!='generated'
     or m['parameters']['top']!=kind or m['parameters']['layout']!=expected
     or not (m['top']==base or m['top'].startswith(base+'_Aq'))):
  raise ValueError(f'{export_id}: export/profile mismatch')
 listed=set()
 for path in m['files']:
  p=Path(path)
  if p.is_absolute() or '..' in p.parts or not (d/p).is_file() or path in listed:
   raise ValueError('bad export file inventory')
  listed.add(path)
 lines=(d/'files.f').read_text().splitlines()
 sv=[x for x in lines if not x.startswith('+incdir+')]
 if len(sv)!=len(set(sv)) or set(sv)!={x for x in listed if x.endswith('.sv')}:
  raise ValueError('bad files.f')
 top=d/'src'/f'{m["top"]}.sv'
 if top.read_text().splitlines()[0]!=f'// RTL_ID: {export_id}':raise ValueError('top RTL_ID mismatch')
 return d,m


def verify_trace(directory,n,schedule):
 rows=list(csv.DictReader((directory/'transactions.txt').open(),delimiter='\t'))
 if len(rows)!=n:raise ValueError('missing/extra transaction trace')
 previous=None
 for i,row in enumerate(rows):
  ac,rc=int(row['accept_cycle']),int(row['result_cycle'])
  if int(row['txn'])!=i or rc-ac!=18 or int(row['latency'])!=18 or int(row['last'])!=int(i==n-1):
   raise ValueError('trace ordering/latency/last mismatch')
  if previous is not None and (ac<=previous or ((schedule=='continuous' or i<32) and ac-previous!=1)):
   raise ValueError('II=1 admission failed')
  previous=ac


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--exports',type=Path,default=ROOT/'hw/test/regressions/lab1-exports.json')
 p.add_argument('--profiles',nargs='+',choices=list(PROFILES),default=list(PROFILES))
 p.add_argument('--datasets',nargs='+',default=DEFAULT_DATASETS)
 p.add_argument('--formats',nargs='+',choices=list(FORMATS),default=list(FORMATS))
 p.add_argument('--schedule',choices=['continuous','bubbles','both'],default='continuous')
 p.add_argument('--data-root',type=Path,default=DATA_ROOT)
 p.add_argument('--summary',type=Path,help='optional named summary; historical summaries are never overwritten by default')
 p.add_argument('--run-id',default='pe-regression-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 a=p.parse_args()
 if Path(a.run_id).name!=a.run_id: p.error('run ID must be one name')
 data_root=a.data_root.resolve()
 exports=json.loads(a.exports.read_text());index=json.loads((data_root/'index.json').read_text())
 run=ROOT/'hw/test/runs'/a.run_id;run.mkdir(parents=True,exist_ok=False)
 report={'schema_version':'dp_pe_report_v2','run_id':a.run_id,'exports':{x:exports[x] for x in a.profiles},
         'datasets':a.datasets,'formats':a.formats,'scope':'listed fixed data only; not full precision/PPA signoff',
         'results_directory':run.relative_to(ROOT).as_posix(),'cases':[],'groups':[],
         'tools':{},'ppa_eligible':False}
 if index.get('sampling_scope')=='normal':
  report.update(sampling_scope='normal',normal_scope_contract=index['normal_scope_contract'])
 for tool in ['iverilog','vvp']:
  result=subprocess.run([tool,'-V'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  report['tools'][tool]=result.stdout.splitlines()[0]
 schedules=['continuous','bubbles'] if a.schedule=='both' else [a.schedule]
 for profile in a.profiles:
  directory,manifest=inspect_export(exports[profile],profile)
  build=run/profile;build.mkdir()
  tb=ROOT/'hw/test/tb'/f'tb_{profile}.sv';sim=build/'sim.vvp'
  cmd=['iverilog','-g2012','-I',str(ROOT/'hw/test/tb/common'),'-s',f'tb_{profile}',
       '-D',f'DUT_MODULE={manifest["top"]}','-o',str(sim),'-f','files.f',str(tb)]
  proc=subprocess.run(cmd,cwd=directory,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  (build/'compile.log').write_text(proc.stdout)
  (build/'run.txt').write_text(f'RTL_ID {exports[profile]}\nTOP {manifest["top"]}\nTB {tb.relative_to(ROOT)}\nCOMMAND '+ ' '.join(cmd)+'\n')
  if proc.returncode:raise RuntimeError(f'compile failed: {build}/compile.log')
  selected=[]
  for entry in index['cases']:
   fmt=entry['format'];k=native_k(profile,fmt)
   if fmt not in a.formats or not k or entry['k']!=k or entry['dataset'] not in a.datasets:continue
   selected.append(entry)
  expected={(fmt,ds) for fmt in a.formats if native_k(profile,fmt) for ds in a.datasets}
  if not expected:raise ValueError('selected profile supports none of the selected formats')
  if not expected.issubset({(x['format'],x['dataset']) for x in selected}):raise ValueError('missing required shared vectors')
  for entry in selected:
   relative=Path(entry['path'])
   if relative.is_absolute() or '..' in relative.parts:raise ValueError('invalid case path')
   case=data_root/relative;meta=validate_case(case)
   if (meta['format'],meta['logical_k'],meta['txn_count'])!=(entry['format'],entry['k'],entry['transactions']):
    raise ValueError('index disagrees with case metadata')
   for schedule in schedules:
    out=build/entry['format']/f'K{entry["k"]}'/case.name/schedule;out.mkdir(parents=True)
    cmd=['vvp',str(sim),f'+INPUT_FILE={case/"inputs.txt"}',f'+OUTPUT_DIR={out}',
         f'+RTL_ID={exports[profile]}',f'+SCHEDULE={int(schedule=="bubbles")}']
    try:
     proc=subprocess.run(cmd,cwd=directory,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
     log=proc.stdout;ok=proc.returncode==0 and 'PROTOCOL_PASS' in log
    except subprocess.TimeoutExpired as err:
     log=str(err)+'\nSIMULATION_TIMEOUT';ok=False
    (out/'simulation.log').write_text(log)
    result={'profile':profile,'rtl_id':exports[profile],'format':entry['format'],'k':entry['k'],
            'dataset':case.name,'schedule':schedule,'golden_model':meta['golden_model'],
            'input':(case/'inputs.txt').relative_to(ROOT).as_posix(),
            'golden':(case/'golden.txt').relative_to(ROOT).as_posix(),'transactions':meta['txn_count'],
            'protocol_passed':ok,'passed':False,'reasons':[]}
    if meta.get('sampling_scope')=='normal':
     result['sampling_scope']='normal'
    if ok:
     verify_trace(out,meta['txn_count'],schedule)
     if meta.get('kind')=='random_exact_1600':
      result.update(compare_random_case(out/'rtl_result.txt',case/'golden.txt',meta['segments'],out))
     else:
      result.update(compare_files(out/'rtl_result.txt',case/'golden.txt',out/'comparison.txt',meta['txn_count']))
      if meta.get('kind')=='merged_fixed_datasets':
       result.update(compare_segments(out/'rtl_result.txt',case/'golden.txt',meta['segments'],out/'segments.txt'))
    else:result['reasons']=['SIM_FAILED']
    result['output_directory']=out.relative_to(ROOT).as_posix()
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    report['cases'].append(result)
    print(f'{profile:9} {entry["format"]:14} K{entry["k"]:<3} {case.name:37} {schedule:10} '
          f'protocol={ok} exact={result.get("exact","NA")}/{meta["txn_count"]} '
          f'maxULP={result.get("max_finite_ulp","NA")} passed={result["passed"]}',flush=True)
   if a.schedule=='both':
    continuous=build/entry['format']/f'K{entry["k"]}'/case.name/'continuous/rtl_result.txt'
    bubbles=continuous.parent.parent/'bubbles/rtl_result.txt'
    if continuous.exists() and bubbles.exists() and continuous.read_bytes()!=bubbles.read_bytes():
     raise ValueError(f'{profile}/{entry["path"]}: schedule-dependent numerical output')
  sim.unlink(missing_ok=True)
 for profile in a.profiles:
  for fmt in FORMATS:
   cases=[x for x in report['cases'] if x['profile']==profile and x['format']==fmt]
   if not cases:continue
   unique={x['input']:x for x in cases}
   items=list(unique.values());n=sum(x['transactions'] for x in items);exact=sum(x.get('exact',0) for x in items)
   precision_n=sum(x.get('precision_transactions',x['transactions']) for x in items)
   precision_exact=sum(x.get('precision_exact',x.get('exact',0)) for x in items)
   group={'profile':profile,'format':fmt,'k':native_k(profile,fmt),'unique_transactions':n,'exact':exact,
          'exact_fraction':exact/n,'max_ulp':max((x.get('max_finite_ulp') or 0 for x in items),default=0),
          'precision_transactions':precision_n,'precision_exact':precision_exact,
          'precision_exact_fraction':precision_exact/precision_n,
          'protocol_passed':all(x['protocol_passed'] for x in cases),
          'passed':all(x['passed'] for x in cases),'case_runs':len(cases)}
   report['groups'].append(group)
 report['passed']=all(x['passed'] for x in report['cases'])
 report['schedules_identical']=(True if a.schedule=='both' else None)
 report['finished_utc']=datetime.now(timezone.utc).isoformat()
 (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 lines=[f'run_id {a.run_id}',f'passed {report["passed"]}','scope '+report['scope']]
 lines += [f'RTL_ID {profile} {identity}' for profile,identity in report['exports'].items()]
 lines+=['profile\tformat\tK\tunique_txns\texact\texact_percent\tmax_ulp\tprotocol\tpassed\tprecision_txns\tprecision_exact']
 for x in report['groups']:
  lines.append('\t'.join(map(str,[x['profile'],x['format'],x['k'],x['unique_transactions'],x['exact'],
              f'{100*x["exact_fraction"]:.4f}',x['max_ulp'],x['protocol_passed'],x['passed'],
              x['precision_transactions'],x['precision_exact']])))
 (run/'report.txt').write_text('\n'.join(lines)+'\n')
 if a.summary:
  a.summary.parent.mkdir(parents=True,exist_ok=True)
  a.summary.write_text(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2)+'\n')
 print('REPORT',run/'report.txt',flush=True)
 return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
