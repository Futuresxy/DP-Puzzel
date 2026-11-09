"""Build-independent precision campaign; existing formats run before extensions."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import platform
import subprocess
import sys

TEST=Path(__file__).resolve().parent
sys.path.insert(0,str(TEST))
from adapters.cmodel import ROOT, DEFAULT_CONFIG, read_inputs, sha256, evaluate
from cases.import_legacy import import_existing
from reference.exact import error_bound_ok, ulp_distance, fp64_tf32
from reference.architecture import reference


def fingerprint(paths):
    h=hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes()+b'\0')
    return h.hexdigest()


def model_fingerprint():
    root=ROOT/'src/cmodel'
    return fingerprint([root/'CMakeLists.txt',root/'main.cpp',
                        *(root/'lib').rglob('*.cpp'),*(root/'lib').rglob('*.hpp'),
                        *(root/'include').rglob('*.hpp')])


def campaign(directories,run,write_goldens=False,binary=None,frontend='multi'):
    reports=[]; failures=[]
    for directory in directories:
        manifest=json.loads((directory/'manifest.json').read_text()); k,requests=read_inputs(directory/'inputs.txt')
        cfg=DEFAULT_CONFIG | dict(k_fp16=k)
        if frontend=='e': cfg['frontend']='e'
        results=evaluate(requests,config=cfg,run_dir=run,binary=binary)
        if manifest['count']!=len(requests) or manifest['input_sha256']!=sha256(directory/'inputs.txt'):
            raise ValueError('input manifest count/hash mismatch')
        saved=[]
        if not write_goldens and (directory/'expected.jsonl').exists():
            saved_cfg={key:value for key,value in cfg.items() if key!='frontend'}
            if manifest['golden']['expected_sha256']!=sha256(directory/'expected.jsonl') or manifest['golden']['config']!=saved_cfg:
                raise ValueError('golden manifest hash/config mismatch')
            saved=[json.loads(line) for line in (directory/'expected.jsonl').read_text().splitlines()]
            if len(saved)!=len(requests): raise ValueError('golden count mismatch')
        source_file=directory/'source_reference.txt'
        source=[int(x,16) for x in source_file.read_text().splitlines()] if source_file.exists() else [None]*len(requests)
        distances=[]; exact_count=0; source_diffs=0; bound_count=0
        expected=[]; per_case=[]; fp64_diffs=[]; fp64_distances=[]
        for r,got,old in zip(requests,results,source):
            mathematical=reference(r,cfg); architecture=reference(r,cfg,True); bits=int(got['d'],16)
            correct=(bits==architecture['bits'] and got['id']==r['id'] and got['last']==r['last'] and got['d_datatype']==r['c_datatype'])
            if not correct: failures.append(dict(format=manifest['format'],id=r['id'],got=got,expected=f"{architecture['bits']:08x}"))
            if r['c_datatype']==1:
                overflow=not -(1<<31)<=mathematical['value'].value<(1<<31)
                if bits!=mathematical['bits'] or got['flags']['integer_overflow']!=overflow:
                    failures.append(dict(format='int8',id=r['id'],reason='integer exactness/overflow'))
                bound_ok=True
            else:
                bound_ok=error_bound_ok(bits,mathematical,architecture)
                if bound_ok is False: failures.append(dict(format=manifest['format'],id=r['id'],reason='derived error bound'))
                if bound_ok: bound_count+=1
                if got['flags']['invalid']!=architecture['value'].invalid:
                    failures.append(dict(format=manifest['format'],id=r['id'],reason='invalid flag'))
            distance=ulp_distance(bits,mathematical['bits']); distances.append(distance)
            exact_count+=bits==mathematical['bits']; source_diffs+=old is not None and old!=mathematical['bits']
            fp64=fp64_tf32(r,cfg) if r['a_datatype']==0 else None
            if fp64 is not None:
                fp64_distances.append(ulp_distance(bits,fp64))
                if fp64!=mathematical['bits']: fp64_diffs.append(r['id'])
            expected.append(dict(id=r['id'],d=f'{bits:08x}',d_datatype=got['d_datatype'],last=got['last'],
                                 exact_fp32_or_int32=f"{mathematical['bits']:08x}",fp64_tf32=None if fp64 is None else f'{fp64:08x}'))
            if saved and expected[-1]!=saved[len(expected)-1]:
                failures.append(dict(format=manifest['format'],id=r['id'],reason='committed golden mismatch'))
            per_case.append(dict(id=r['id'],model=f'{bits:08x}',exact=f"{mathematical['bits']:08x}",
                                 ulp=distance,bound_ok=bound_ok,architecture_match=correct,flags=got['flags']))
        segments=[]
        for seg in manifest.get('segments',[]):
            ds=distances[seg['start']:seg['stop']]
            segments.append(dict(name=seg['dataset'],count=len(ds),exact=sum(d==0 for d in ds),
                                 max_ulp=max((d for d in ds if d is not None),default=None)))
            if seg.get('require_bit_exact') and any(d!=0 for d in ds):
                failures.append(dict(format=manifest['format'],reason='ones not exact'))
        row=dict(format=manifest['format'],logical_k=manifest['logical_k'],count=len(results),
                 architecture_mismatches=sum(not p['architecture_match'] for p in per_case),
                 exact_count=exact_count,at_most_1_ulp=sum(d is not None and d<=1 for d in distances),
                 max_ulp=max((d for d in distances if d is not None),default=None),
                 nonfinite_comparison_count=sum(d is None for d in distances),
                 finite_bound_checks=bound_count,source_reference_vs_exact_differences=source_diffs,
                 fp64_vs_exact_differences=len(fp64_diffs),fp64_vs_exact_difference_ids=fp64_diffs,
                 model_vs_fp64_count=len(fp64_distances),model_vs_fp64_at_most_1_ulp=sum(d is not None and d<=1 for d in fp64_distances),
                 model_vs_fp64_max_ulp=max((d for d in fp64_distances if d is not None),default=None),segments=segments,
                 input_sha256=sha256(directory/'inputs.txt'))
        reports.append(row)
        (run/f"{manifest['format']}-cases.jsonl").write_text(''.join(json.dumps(x)+'\n' for x in per_case))
        if write_goldens and not failures:
            (directory/'expected.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in expected))
            manifest['golden']=dict(config=cfg,model_source_sha256=model_fingerprint(),
                                   expected_sha256=sha256(directory/'expected.jsonl'),
                                   reference='independent Fraction finite-window oracle + exact mathematical reference',
                                   status='cmodel_verified_not_rtl')
            (directory/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        print(f"{row['format']:16} K{row['logical_k']:2} n={row['count']} architecture_fail={row['architecture_mismatches']} exact={exact_count} max_ulp={row['max_ulp']}",flush=True)
    return dict(formats=reports,failures=failures,status='passed' if not failures else 'failed')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['existing','extensions','all'],default='existing')
    ap.add_argument('--frontend',choices=['multi','e'],default='multi')
    ap.add_argument('--write-goldens',action='store_true')
    ap.add_argument('--import-existing',type=Path,metavar='SOURCE_ROOT',help='Import from an external legacy vector corpus')
    ap.add_argument('--binary',type=Path,default=ROOT/'src/cmodel/build/dp_cmodel_cli')
    ap.add_argument('--run-dir',type=Path)
    args=ap.parse_args()
    if args.frontend=='e' and args.write_goldens:
        ap.error('E frontend checks the shared saved results; it must not overwrite multi goldens')
    if args.frontend=='e' and args.phase=='extensions':
        ap.error('E frontend uses the existing MXFP4/NVFP4/HiF4 datasets')
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run=args.run_dir or TEST/'runs/cmodel'/run_id
    run.mkdir(parents=True,exist_ok=args.run_dir is not None)
    if args.import_existing: import_existing(args.import_existing)
    directories=sorted((TEST/'data/dp').glob('*/K*/correct_961')) if args.phase!='extensions' else []
    if args.phase!='existing': directories+=sorted((TEST/'data/dp').glob('*/K*/generated_v1'))
    if args.frontend=='e':
        directories=[p for p in directories if p.parent.parent.name in ('mxfp4_e2m1','nvfp4','hif4')]
    if not directories: raise RuntimeError('no datasets; import/generate them first')
    print(f'Frontend: {args.frontend}',flush=True)
    report=campaign(directories,run,args.write_goldens,args.binary,args.frontend)
    config=DEFAULT_CONFIG | ({'frontend':'e'} if args.frontend=='e' else {})
    report.update(config=config,phase=args.phase,frontend=args.frontend,python=platform.python_version(),
                  model_version=json.loads(subprocess.check_output([str(args.binary),'--version'],text=True)),
                  model_source_sha256=model_fingerprint(),
                  scope='CModel and independent mathematical checks; no RTL or EDA')
    summary=run/'summary.json'
    temporary=summary.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,indent=2)+'\n')
    temporary.replace(summary)
    print(f'Report: {summary}')
    if report['failures']:
        print(json.dumps(report['failures'][:10],indent=2)); return 1
    return 0


if __name__=='__main__': sys.exit(main())
