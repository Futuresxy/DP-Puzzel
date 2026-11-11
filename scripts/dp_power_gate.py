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


def original_dc_receipt(root, point, resolved, fingerprint, frontend, verification_id=None):
    """Use DC's pinned receipt even after a later regression of identical RTL.

    The export manifest tracks latest validation. Historical DC acceptance is
    bound to a specific complete receipt, and never grants current eligibility.
    """
    if verification_id is None:
        verification_id = resolved['gate']['verification_id']
    require(isinstance(verification_id, str) and
            re.fullmatch(r'\d{8}T\d{12}Z', verification_id), 'Invalid original verification ID')
    path = contained(root, 'test/runs/verilog/' + verification_id + '/verification.json')
    receipt = read_json(path)
    require(receipt['verification_id'] == verification_id and
            receipt['export_id'] == point['export_id'] and receipt['rtl_fingerprint'] == fingerprint and
            receipt['status'] == 'passed' and receipt['method'] == 'verilog_testbench' and
            receipt['numerical_pass'] is True and receipt['protocol_pass'] is True and
            receipt['parameters'] == PARAMETERS and receipt['phase'] == 'all' and
            receipt['latency'] == 8 and receipt['ii'] == 1 and
            receipt.get('frontend', 'multi') == frontend and receipt['seeds'] == [20271105],
            'Original complete regression mismatch')
    require(receipt['command'] and receipt['simulator']['name'] == 'verilator' and
            receipt['simulator']['version'], 'Missing original simulator provenance')
    require(all(row['export_id'] == point['export_id'] for row in receipt['scopes']),
            'Original scope export mismatch')
    started = datetime.fromisoformat(receipt['started_utc']).timestamp()
    finished = datetime.fromisoformat(receipt['finished_utc']).timestamp()
    require(started <= finished, 'Invalid original verification times')
    validate_scopes(receipt['scopes'], root, started, finished, frontend)
    return path


def frozen_dc_source(root, point, *, retired_repair=None):
    root = Path(root).resolve()
    require(isinstance(point.get('original_verification_id'), str) and
            re.fullmatch(r'\d{8}T\d{12}Z', point['original_verification_id']),
            'Invalid original verification ID')
    export = contained(root / 'hw/rtl', point['export_id'])
    manifest = read_json(export / 'manifest.json')
    frontend = manifest.get('frontend', 'multi')
    require(manifest['top'] == point['top'] and manifest['interface'] == DP_INTERFACE,
            'Frozen top/interface mismatch')
    # Original acceptance comes from DC's pinned complete receipt below; latest
    # manifest status may legitimately change during an identical-RTL rerun.
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
    run = contained(root, point['dc_run'])
    resolved_path = run / 'inputs/resolved.json'
    resolved = read_json(resolved_path)
    require(resolved['gate']['rtl_fingerprint'] == fingerprint and
            resolved['gate']['export_id'] == export.name and resolved['gate']['top'] == point['top'] and
            resolved['gate']['parameters'] == PARAMETERS, 'DC source binding mismatch')
    receipt_path = original_dc_receipt(root, point, resolved, fingerprint, frontend)
    additional = {}
    if point['original_verification_id'] != resolved['gate']['verification_id']:
        # Some historical power points recorded a later complete regression of
        # exactly the same source. Validate both; never let the newer receipt
        # substitute for the receipt DC actually accepted.
        additional_path = original_dc_receipt(root, point, resolved, fingerprint, frontend,
                                               point['original_verification_id'])
        require(datetime.fromisoformat(read_json(additional_path)['finished_utc']) >=
                datetime.fromisoformat(read_json(receipt_path)['finished_utc']),
                'Additional verification predates original DC acceptance')
        additional = dict(additional_verification_id=point['original_verification_id'],
                          additional_receipt_sha256=digest(additional_path))
    # Re-analyze final reports. Completed campaign reporting may use a receipt
    # from the last verification of a deliberately retired repair source.
    import sys
    sys.path.insert(0, str(root / 'hw/dc_syn/scripts'))
    from report_dc import analyze
    from run_dc import verify_repair_source
    require(analyze(run, resolved)['flow_pass'], 'Original DC result is not passing')
    if retired_repair is None:
        verify_repair_source(resolved)
    else:
        repair = (resolved.get('design_rule_repair') or resolved.get('hold_repair')
                  or resolved.get('timing_repair'))
        require(repair and repair['source_run'] == retired_repair['source_run'] and
                retired_repair['verified_before_retirement'] is True and
                digest(resolved_path) == retired_repair['final_resolved_sha256'],
                'Retired repair receipt does not match final DC input')
    for artifact in point['artifacts'].values():
        path = contained(root, artifact['path'])
        require(run in path.parents and digest(path) == artifact['sha256'], 'Mapped artifact changed')
    return dict(export_id=export.name, top=point['top'], rtl_fingerprint=fingerprint,
                sources=[str(export / name) for name in sources],
                include_dirs=[str(export / 'src/src/verilog/parameter')],
                original_receipt_sha256=digest(receipt_path), parameters=PARAMETERS,
                scope='archived_dc_reuse_only', resolved=resolved, **additional)


def verify_workload_replay(root, point, receipt_path, *, retired_repair=None, retained_dataset=None):
    if retired_repair is None:
        gate = frozen_dc_source(root, point)
    else:
        gate = frozen_dc_source(root, point, retired_repair=retired_repair)
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
    relocated = {}
    if retained_dataset is not None:
        relocated = {str(Path(point['dataset_directory']) / name): contained(retained_dataset, name)
                     for name in point['dataset_files_sha256']}
    for name, expected in receipt['files_sha256'].items():
        path = relocated[name] if name in relocated else contained(root, name)
        require(digest(path) == expected, 'Workload replay input/output changed: ' + name)
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
