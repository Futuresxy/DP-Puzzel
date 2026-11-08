"""Explicit archived-DC reuse gate, separate from current-source synthesis eligibility.

An archived source keeps its original complete regression and additionally needs
a fresh bit-exact workload replay. This never changes an old manifest or admits
the working tree to synthesis using a historical receipt.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from rtl_gate import contained, read_json, require, rtl_fingerprint
from dp_rtl_gate import DP_INTERFACE, PARAMETERS, frontend_prefix, validate_scopes


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_dc_source(root, point):
    root = Path(root).resolve()
    export = contained(root / 'hw/rtl', point['export_id'])
    manifest = read_json(export / 'manifest.json')
    frontend = manifest.get('frontend', 'multi')
    require(manifest['top'] == point['top'] and manifest['interface'] == DP_INTERFACE,
            'Frozen top/interface mismatch')
    require(manifest['status'] == 'passed' and manifest['ppa_eligible'] is True,
            'Original export never passed complete RTL regression')
    fingerprint = rtl_fingerprint(export)
    require(fingerprint == manifest['rtl_fingerprint'], 'Frozen RTL fingerprint changed')
    source_hashes = manifest['source_sha256']
    source_fingerprint = hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest()
    require(manifest['source_fingerprint'] == source_fingerprint and
            export.name == frontend_prefix(frontend) + source_fingerprint[:16], 'Source identity changed')
    require({str(p.relative_to(export)) for p in (export / 'src').rglob('*') if p.is_file()}
            == {'src/' + name for name in source_hashes}, 'Frozen payload inventory changed')
    for name, expected in source_hashes.items():
        content = contained(export, 'src/' + name).read_bytes()
        prefix = ('// RTL_ID: ' + export.name + '\n').encode()
        require(content.startswith(prefix) and hashlib.sha256(content[len(prefix):]).hexdigest() == expected,
                'Frozen source bytes changed: ' + name)
    lines = (export / 'files.f').read_text().splitlines()
    require(lines[0] == '+incdir+src/src/verilog/parameter', 'Unexpected frozen include directory')
    sources = lines[1:]
    require(len(sources) == len(set(sources)) and set(sources) ==
            {'src/' + name for name in source_hashes if name.endswith('.v')}, 'Frozen filelist mismatch')
    for name in sources:
        require('/systemverilog/' not in name, 'Frozen SV cannot be substituted')
        contained(export, name)
    receipt_path = contained(root, manifest['verification']['path'])
    receipt = read_json(receipt_path)
    require(receipt['verification_id'] == point['original_verification_id'] and
            receipt['export_id'] == export.name and receipt['rtl_fingerprint'] == fingerprint and
            receipt['status'] == 'passed' and receipt['numerical_pass'] and receipt['protocol_pass'] and
            receipt['parameters'] == PARAMETERS and receipt['phase'] == 'all' and
            receipt['latency'] == 8 and receipt['ii'] == 1, 'Original complete regression mismatch')
    validate_scopes(receipt['scopes'], root, datetime.fromisoformat(receipt['started_utc']).timestamp(),
                    datetime.fromisoformat(receipt['finished_utc']).timestamp(), frontend)
    run = contained(root, point['dc_run'])
    resolved = read_json(run / 'inputs/resolved.json')
    require(resolved['gate']['rtl_fingerprint'] == fingerprint and
            resolved['gate']['export_id'] == export.name and resolved['gate']['top'] == point['top'] and
            resolved['gate']['parameters'] == PARAMETERS, 'DC source binding mismatch')
    # Re-analyze reports and verify the preserved repair chain; no tool launch.
    import sys
    sys.path.insert(0, str(root / 'hw/dc_syn/scripts'))
    from report_dc import analyze
    from run_dc import verify_repair_source
    require(analyze(run, resolved)['flow_pass'], 'Original DC result is not passing')
    verify_repair_source(resolved)
    for artifact in point['artifacts'].values():
        path = contained(root, artifact['path'])
        require(run in path.parents and digest(path) == artifact['sha256'], 'Mapped artifact changed')
    return dict(export_id=export.name, top=point['top'], rtl_fingerprint=fingerprint,
                sources=[str(export / name) for name in sources],
                include_dirs=[str(export / 'src/src/verilog/parameter')],
                original_receipt_sha256=digest(receipt_path), parameters=PARAMETERS,
                scope='archived_dc_reuse_only', resolved=resolved)


def verify_workload_replay(root, point, receipt_path):
    gate = frozen_dc_source(root, point)
    root = Path(root).resolve()
    receipt = read_json(receipt_path)
    require(receipt['status'] == 'passed' and receipt['method'] == 'verilog_testbench' and
            receipt['export_id'] == point['export_id'] and
            receipt['rtl_fingerprint'] == gate['rtl_fingerprint'] and
            receipt['top'] == point['top'] and receipt['format'] == point['format'] and
            receipt['logical_k'] == point['logical_k'] and receipt['latency'] == 8 and receipt['ii'] == 1,
            'Workload replay scope mismatch')
    require(receipt['simulator_version'] and receipt['commands'], 'Missing actual simulation provenance')
    require(all(receipt[field] in receipt['files_sha256'] for field in
                ('simulation_log', 'expected_file', 'results_file')), 'Unhashed replay evidence')
    for name, expected in receipt['files_sha256'].items():
        require(digest(contained(root, name)) == expected, 'Workload replay input/output changed: ' + name)
    log = contained(root, receipt['simulation_log']).read_text()
    require(not re.search(r'\bFAIL\b|FATAL|ERROR', log), 'Failed workload simulation')
    count = receipt['total_transactions']
    require(receipt['workload_transactions'] == 1024 and count > 1024 and
            f'POWER_SIM_PASS accepted={count} checked={count} workload=1024 latency=8' in log,
            'Incomplete workload/protocol replay')
    expected = contained(root, receipt['expected_file']).read_text().splitlines()
    rows = contained(root, receipt['results_file']).read_text().splitlines()
    require(len(rows) == len(expected) == count, 'Workload output count changed')
    for index, (actual, golden) in enumerate(zip(rows, expected)):
        fields = actual.split()
        require(len(fields) == 4 and int(fields[0]) == index and fields[1:] == golden.split(),
                'Workload output mismatch')
    return gate
