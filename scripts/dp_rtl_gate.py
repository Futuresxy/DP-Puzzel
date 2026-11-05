"""Gate the DP v1 source-snapshot contract using a fresh, complete RTL campaign.

Legacy source SHA fields remain compatible with the RTL branch. DC consumes one
fingerprint of files.f + src/, explicit parameters, and a real regression receipt.
"""
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime
from rtl_gate import contained, read_json, require, rtl_fingerprint

PARAMETERS = {'K_FP16': 16, 'LOCAL_W': 28, 'GLOBAL_W': 40}
DEFAULT_SCOPE = (PARAMETERS['K_FP16'], PARAMETERS['LOCAL_W'], PARAMETERS['GLOBAL_W'])
DP_INTERFACE = {'clock_port': 'clock', 'reset_port': 'reset',
                'reset_kind': 'synchronous', 'reset_active': 'high'}
CONFIGS = ((4,27,40), (8,27,40), DEFAULT_SCOPE, (4,28,48), (8,32,64), (16,32,64))


def verification_inputs(root):
    paths = []
    for base in ('test', 'src/cmodel'):
        paths += [p for p in (root/base).rglob('*') if p.is_file()
                  and not {'runs', 'results', 'build', '__pycache__'} & set(p.relative_to(root/base).parts)
                  and p.suffix != '.md']
    paths.append(root/'src/cmodel/build/dp_cmodel_cli')
    paths += sorted((root/'src/configs/dp').glob('*.json'))
    paths += [root/'scripts/dp_rtl_gate.py',root/'scripts/rtl_gate.py']
    return sorted(paths)


def payload(export, root):
    manifest = read_json(export/'manifest.json')
    frontend=manifest.get('frontend','multi')
    require(frontend in ('multi','e'), 'Unknown DP frontend')
    top='dp_top_e' if frontend=='e' else 'dp_top'
    require(manifest['export_id'] == export.name and manifest['implementation'] == 'verilog'
            and manifest['top'] == top, 'DP identity mismatch')
    require(manifest.get('interface', DP_INTERFACE) == DP_INTERFACE, 'DP clock/reset contract mismatch')
    lines = (root/'src/verilog'/('files_e.f' if frontend=='e' else 'files.f')).read_text().splitlines()
    require(lines[0] == '+incdir+src/verilog/parameter', 'Unexpected DP include path')
    sources = lines[1:]
    require(sources and len(set(sources)) == len(sources)
            and all(s.startswith('src/verilog/') and s.endswith('.v')
                    and '/systemverilog/' not in s for s in sources), 'Invalid pure Verilog source list')
    headers = sorted(str(p.relative_to(root)) for p in (root/'src/verilog/parameter').glob('*.vh'))
    names = sources + headers
    hashes = {n: hashlib.sha256(contained(root,n).read_bytes()).hexdigest() for n in names}
    fp = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    require(manifest['source_sha256'] == hashes and manifest['source_fingerprint'] == fp
            and export.name == ('DP_verilog_e_' if frontend=='e' else 'DP_verilog_')+fp[:16], 'DP source fingerprint mismatch')
    expected_list = ['+incdir+src/src/verilog/parameter'] + ['src/'+s for s in sources]
    require((export/'files.f').read_text().splitlines() == expected_list, 'DP files.f mismatch')
    require({str(p.relative_to(export)) for p in (export/'src').rglob('*') if p.is_file()}
            == {'src/'+n for n in names}, 'Unexpected/missing DP payload')
    for n in names:
        expected = ('// RTL_ID: '+export.name+'\n').encode() + contained(root,n).read_bytes()
        require(contained(export,'src/'+n).read_bytes() == expected, 'Modified DP snapshot: '+n)
    return manifest, rtl_fingerprint(export), [str(export/'src'/n) for n in sources]


def validate_scopes(scopes, root, started, finished, frontend='multi'):
    e=frontend=='e'
    required=10 if e else 17
    require(len(scopes) == required, 'Full DP campaign requires all formats, parameter runs and E directed coverage')
    require(len({r['name'] for r in scopes}) == required, 'Duplicate DP campaign')
    if e:
        require({r['name'] for r in scopes if not r['name'].startswith('mixed-')} ==
                {'mxfp4_e2m1','nvfp4','hif4','directed-e'}, 'Missing E numerical coverage')
    mixed = [r for r in scopes if r['name'].startswith('mixed-')]
    require({(r['k_fp16'],r['local_width'],r['global_width']) for r in mixed} == set(CONFIGS),
            'Missing parameter/cycle coverage')
    total = 0
    for r in scopes:
        require(r['simulator'] == 'verilator' and r['implementation'] == 'verilog', 'PPA requires linted Verilog campaign')
        require(r.get('frontend','multi')==frontend, 'Campaign frontend mismatch')
        log = contained(root,r['simulation_log'])
        text = log.read_text()
        require(r['result'] in text and not re.search(r'\bFAIL\b|%Error|FATAL',text), 'Missing/failed simulator evidence')
        match = re.fullmatch(r'PASS cycles=(\d+) accepted=(\d+) checked=(\d+) cancelled=(\d+)',r['result'])
        require(match, 'Invalid simulator PASS counters')
        _, accepted, checked, cancelled = map(int,match.groups())
        require(checked > 0 and accepted == checked+cancelled, 'Invalid transaction counts')
        if r in mixed:
            require((accepted,checked,cancelled) == ((144,137,7) if e else (528,487,41)) and r['cutpoints_checked'] > 0,
                    'Incomplete mixed-format/reset coverage')
        else:
            require((r['k_fp16'],r['local_width'],r['global_width']) == DEFAULT_SCOPE, 'Wrong default parameters')
            if r['name']=='directed-e':
                require(checked==5288 and accepted==checked and cancelled==0 and r['cutpoints_checked']==1010008,
                        'Incomplete E element/metadata/boundary coverage')
            else:
                if e: require(checked==961, 'Incomplete E per-format vectors')
                total += checked
        for key in ('simulation_log','lint_log','compile_log','results_path','input_path','golden_path','schedule_path'):
            p = contained(root,r[key])
            require(p.stat().st_mtime <= finished, 'Campaign artifact changed: '+r[key])
        require(started <= log.stat().st_mtime <= finished, 'Stale simulation log')
        require(not re.search(r'%Error|%Warning', contained(root,r['lint_log']).read_text()), 'RTL lint is not clean')
        for key, digest in (('results_path','output_sha256'),('input_path','input_sha256')):
            require(hashlib.sha256(contained(root,r[key]).read_bytes()).hexdigest() == r[digest], 'Campaign data mismatch')
    require(total == (2883 if e else 10747), 'Missing default-format numerical coverage')
    require(sum(r['cutpoints_checked'] for r in mixed) == (96916 if e else 231654),
            'Incomplete numerical cutpoint coverage')


def verify_dp_export(export_id, root):
    require(re.fullmatch(r'DP_verilog_(?:e_)?[0-9a-f]{16}',export_id), 'Invalid DP export ID')
    export = contained(root/'hw/rtl',export_id)
    m, fp, sources = payload(export,root)
    frontend=m.get('frontend','multi')
    require(m.get('status') == 'passed' and m.get('ppa_eligible') is True, 'DP has no backend-eligible regression')
    require(m.get('rtl_fingerprint') == fp, 'DP RTL directory fingerprint mismatch')
    receipt_path = contained(root,m['verification']['path'])
    require(root/'test/runs/verilog' in receipt_path.parents, 'Wrong DP evidence location')
    e = read_json(receipt_path)
    require(e['export_id'] == export_id and e['rtl_fingerprint'] == fp
            and e['status'] == 'passed' and e['method'] == 'verilog_testbench'
            and e['numerical_pass'] is True and e['protocol_pass'] is True, 'Invalid DP verification receipt')
    require(e['parameters'] == PARAMETERS and e['latency'] == 8 and e['ii'] == 1
            and e['phase'] == 'all' and e['seeds'] == [20271105]
            and e.get('frontend','multi')==frontend, 'Wrong DP validated scope')
    require(e['simulator']['version'] and e['command'], 'Missing simulator provenance')
    started = datetime.fromisoformat(e['started_utc']).timestamp()
    finished = datetime.fromisoformat(e['finished_utc']).timestamp()
    require(started <= finished, 'Invalid verification times')
    paths = verification_inputs(root)
    binary_time = (root/'src/cmodel/build/dp_cmodel_cli').stat().st_mtime
    require(all(p.stat().st_mtime <= binary_time for p in paths
                if root/'src/cmodel' in p.parents and p.suffix in ('.cpp', '.hpp', '.h')),
            'CModel binary is older than its sources; rebuild and rerun')
    require(e['inputs'] == [str(p.relative_to(root)) for p in paths], 'Verification inputs changed')
    for p in paths:
        require(p.stat().st_mtime <= started, 'Verification input changed; rerun: '+str(p.relative_to(root)))
    validate_scopes(e['scopes'],root,started,finished,frontend)
    require(all(r['export_id'] == export_id for r in e['scopes']), 'Campaign export mismatch')
    return dict(export_id=export_id,top=m['top'],frontend=frontend,export_dir=str(export),rtl_fingerprint=fp,
                sources=sources,include_dirs=[str(export/'src/src/verilog/parameter')],
                language='verilog',parameters=PARAMETERS,verification_id=e['verification_id'],
                clock_port=DP_INTERFACE['clock_port'])
