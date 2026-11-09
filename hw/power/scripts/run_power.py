#!/usr/bin/env python3
"""Sequential frozen-DP RTL/GLS -> native SAIF -> Power Compiler campaign.

Run IDs and selected synthesis inputs are explicit. Library paths are local only.
Every numerical result must pass the shared archived-input gate and pin audit.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
POWER = ROOT / 'hw/power'
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'test')]
from rtl_gate import verify_power_input
from dp_power_gate import frozen_dc_source
from adapters.cmodel import FIELDS, evaluate, read_inputs
from adapters.logical import read_logical_inputs
from reference.exact import DTYPES


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def now():
    return datetime.now(timezone.utc).isoformat()


def finish_state(state, status):
    state.update(status=status, phase='failed' if status == 'failed' else 'finished',
                 finished_utc=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))


def dependencies():
    manifest = json.loads((ROOT / 'dependencies/petile-power.json').read_text())
    directory = ROOT / manifest['directory']
    for name, entry in manifest['files'].items():
        if digest(directory / name) != entry['sha256']:
            raise ValueError('Pinned power dependency changed: ' + name)
    sys.path.insert(0, str(directory))


def execute(command, cwd, logfile, environment=None):
    cwd.mkdir(parents=True, exist_ok=True)
    actual = command
    if environment:
        actual = ['bash', '-c', 'source ' + shlex.quote(environment) +
                  ' >/dev/null 2>&1\nexec ' + shlex.join(list(map(str, command)))]
    with logfile.open('w') as stream:
        stream.write('COMMAND ' + shlex.join(list(map(str, command))) + '\n')
        stream.flush()
        result = subprocess.run(actual, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, timeout=3600)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {logfile.relative_to(ROOT)}')


def check_data(point):
    directory = ROOT / point['dataset_directory']
    if digest(directory / 'manifest.json') != point['dataset_manifest_sha256']:
        raise ValueError('Changed dataset manifest')
    for name, expected in point['dataset_files_sha256'].items():
        if digest(directory / name) != expected:
            raise ValueError('Changed dataset input/golden')
    manifest = json.loads((directory / 'manifest.json').read_text())
    if 'cmodel_config' in point and manifest.get('cmodel_config') != point['cmodel_config']:
        raise ValueError('Dataset/reference model configurations differ')
    reference = point.get('reference_model')
    source_root = ROOT
    binary = ROOT / 'src/cmodel/build/dp_cmodel_cli'
    if reference:
        # Explicit immutable reference input permits parallel source development.
        # Frozen RTL and workload replay gates remain mandatory and unchanged.
        archive = (ROOT / reference['directory']).resolve()
        if not archive.is_relative_to(ROOT.resolve()):
            raise ValueError('Archived reference must be inside the project')
        if digest(archive / 'reference.json') != reference['manifest_sha256']:
            raise ValueError('Archived reference manifest changed')
        recorded = json.loads((archive / 'reference.json').read_text())
        if recorded['sources'] != manifest['cmodel_sources']:
            raise ValueError('Dataset/reference source identities differ')
        if recorded['binary_sha256'] != manifest['cmodel_binary_sha256']:
            raise ValueError('Dataset/reference executable identities differ')
        source_root = archive / 'sources'
        binary = archive / 'dp_cmodel_cli'
    for name, expected in manifest['cmodel_sources'].items():
        source = (source_root / name).resolve()
        if not source.is_relative_to(source_root.resolve()):
            raise ValueError('Reference source path escapes its snapshot')
        if digest(source) != expected:
            raise ValueError('CModel source no longer matches saved expected data')
    if digest(binary) != manifest['cmodel_binary_sha256']:
        raise ValueError('CModel binary changed; regenerate validated goldens')
    requests = (read_inputs(directory / 'inputs.txt')[1] if (directory / 'inputs.txt').exists()
                else read_logical_inputs(directory)[1])
    expected = [json.loads(line) for line in (directory / 'expected.jsonl').read_text().splitlines()]
    if len(requests) != 1024 or len(expected) != 1024:
        raise ValueError('Expected 1024 unique transactions')
    return requests, expected


def reference_config(point):
    """Use the same explicit architecture contract for initialization and data."""
    config = dict(point.get('cmodel_config', {}))
    if config.get('frontend', point['cmodel_frontend']) != point['cmodel_frontend']:
        raise ValueError('Conflicting reference frontend')
    if 'architecture_v19' in config and not isinstance(config['architecture_v19'], bool):
        raise ValueError('architecture_v19 must be an explicit boolean')
    config['frontend'] = point['cmodel_frontend']
    return config


def prepare_vectors(point, work, groups):
    requests, expected = check_data(point)
    frontend = point['cmodel_frontend']
    modes = list(DTYPES)
    if frontend == 'e':
        modes = ['mxfp4_e2m1', 'nvfp4', 'hif4']
    elif frontend == 'qe':
        modes = [mode for mode in modes if 3 <= DTYPES[mode] <= 9]
    initial = []
    for mode in modes:
        datatype = DTYPES[mode]
        kind = 0 if datatype in (0, 1, 2, 10) else 2 if datatype == 8 else 3 if datatype == 9 else 1
        scale = 0 if kind == 0 else 56 if kind == 2 else 192 if kind == 3 else 127
        packed_scale = format(sum(scale << (8 * index) for index in range(groups)), 'x')
        for _ in range(16):
            initial.append(dict(id=len(initial), a_datatype=datatype, b_datatype=datatype,
                                c_datatype=int(datatype == 10), a_scale_datatype=kind,
                                b_scale_datatype=kind, last=False, a='0', b='0', c='00000000',
                                a_scale=packed_scale, b_scale=packed_scale,
                                a_e1='0', a_e2='0', b_e1='0', b_e2='0'))
    reference = point.get('reference_model')
    binary = ROOT / reference['directory'] / 'dp_cmodel_cli' if reference else None
    initial_results = evaluate(initial, config=reference_config(point), run_dir=work / 'reference', binary=binary)
    all_requests = initial + requests
    all_results = initial_results + [dict(d=row['cmodel_results'][frontend], d_datatype=0,
                                          last=row['last']) for row in expected]
    widths = dict(a=groups*64, b=groups*64, c=32, a_scale=groups*8, b_scale=groups*8,
                  a_e1=groups*4, a_e2=groups*2, b_e1=groups*4, b_e2=groups*2)
    vectors = [f'{len(all_requests)} {len(initial)}']
    goldens = []
    for request, result in zip(all_requests, all_results):
        if request['a_datatype'] != request['b_datatype'] or request['a_scale_datatype'] != request['b_scale_datatype']:
            raise ValueError('Unsupported unequal operand types')
        for name, width in widths.items():
            if int(request[name], 16) >= 1 << width:
                raise ValueError('Stimulus exceeds physical port width')
        vectors.append(' '.join([str(request['a_datatype']), str(request['c_datatype']),
                                 str(request['a_scale_datatype']), str(int(request['last']))] +
                                [f'{int(request[name],16):0{(width+3)//4}x}' for name,width in widths.items()]))
        goldens.append(f"{result['d']} {result['d_datatype']} {int(result['last'])}")
    (work / 'vectors.txt').write_text('\n'.join(vectors) + '\n')
    (work / 'expected.txt').write_text('\n'.join(goldens) + '\n')
    save(work / 'initialization.json', dict(modes=modes, per_mode=16, count=len(initial),
                                          policy='legal all-zero data/unit scale; no forced internal state'))
    return len(all_requests)


def compile_design(campaign, work, point, gate, machine):
    top = point['top']
    groups = 6 if top.endswith('e96') else 8 if top.endswith(('e128', 'e128_opt')) else 4
    template = (POWER / 'tb/dp_power_tb.sv.in').read_text()
    bench = template.replace('@TOP@', top).replace('@GROUPS@', str(groups))
    (work / 'tb.sv').write_text(bench)
    key = hashlib.sha256((bench + gate['rtl_fingerprint'] +
                          json.dumps(machine, sort_keys=True)).encode()).hexdigest()[:12]
    build = campaign / 'build' / (top + '_' + key)
    build.mkdir(parents=True, exist_ok=True)
    if not (build / 'complete.json').exists():
        (build / 'tb.sv').write_text(bench)
        rtl_command = [machine['iverilog'], '-g2012', '-s', 'dp_power_tb', '-o', str(build / 'rtl.vvp')]
        for directory in gate['include_dirs']:
            rtl_command += ['-I', directory]
        rtl_command += [str(build / 'tb.sv')] + gate['sources']
        execute(rtl_command, build, build / 'rtl_compile.log')
        netlist = ROOT / point['artifacts']['mapped_verilog']['path']
        command = [machine['vcs'], '-full64', '-sverilog', '-debug_access+all', '+vcs+saif_libcell',
                   '+define+POWER_NATIVE_SAIF', '+notimingcheck', '+delay_mode_zero', '-timescale=1fs/1fs',
                   '-top', 'dp_power_tb', str(build / 'tb.sv'), str(netlist), *machine['cell_models'],
                   '-o', str(build / 'simv')]
        execute(command, build, build / 'gate_compile.log', machine['setup_script'])
        save(build / 'complete.json', dict(key=key, rtl_command=rtl_command, gate_command=command,
                                           rtl_binary_sha256=digest(build / 'rtl.vvp'),
                                           gate_binary_sha256=digest(build / 'simv')))
    compiled = json.loads((build / 'complete.json').read_text())
    if digest(build / 'rtl.vvp') != compiled['rtl_binary_sha256'] or digest(build / 'simv') != compiled['gate_binary_sha256']:
        raise ValueError('Cached simulation executable changed')
    return build, compiled, groups


def check_simulation(work, directory, count, saif=False):
    text = (directory / 'simulation.log').read_text()
    marker = f'POWER_SIM_PASS accepted={count} checked={count} workload=1024 latency=8'
    if marker not in text or 'POWER_INIT_PASS' not in text or re.search(r'\bFAIL\b|FATAL|ERROR', text):
        raise ValueError('Simulation counters/init/protocol failed: ' + str(directory))
    if saif and 'POWER_SAIF_PASS duration_fs=512000000' not in text:
        raise ValueError('SAIF capture did not finish')
    expected = (work / 'expected.txt').read_text().splitlines()
    rows = (directory / 'results.txt').read_text().splitlines()
    if len(rows) != count:
        raise ValueError('Missing numerical results')
    for index, (actual, golden) in enumerate(zip(rows, expected)):
        if actual.split() != [str(index)] + golden.split():
            raise ValueError('Numerical result file differs')


def replay_receipt(point, work, gate, compiled, count, version):
    files = [work / 'vectors.txt', work / 'expected.txt', work / 'tb.sv',
             work / 'rtl/results.txt', work / 'rtl/simulation.log', work / 'initialization.json']
    files += [ROOT / point['dataset_directory'] / name for name in point['dataset_files_sha256']]
    receipt = dict(status='passed', method='verilog_testbench', export_id=point['export_id'],
                   rtl_fingerprint=gate['rtl_fingerprint'], top=point['top'], format=point['format'],
                   logical_k=point['logical_k'], latency=8, ii=1, total_transactions=count,
                   workload_transactions=1024, simulator_version=version, commands=compiled['rtl_command'],
                   simulation_log=str((work / 'rtl/simulation.log').relative_to(ROOT)),
                   expected_file=str((work / 'expected.txt').relative_to(ROOT)),
                   results_file=str((work / 'rtl/results.txt').relative_to(ROOT)),
                   files_sha256={str(path.relative_to(ROOT)): digest(path) for path in files}, finished_utc=now())
    path = ROOT / 'test/runs/power' / work.parent.name / work.name / 'verification.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, receipt)
    return path


def measure(point, work, gate, machine):
    from netlist_activity import power_pin_scopes
    from saif_activity import read_saif, expand_leaf_aliases, write_saif, audit_saif
    from power_report import tcl, parse_power, pin_activities
    scope = 'dp_power_tb/dut'
    netlist = ROOT / point['artifacts']['mapped_verilog']['path']
    scopes = power_pin_scopes(netlist, [Path(p) for p in machine['cell_models']], point['top'], scope)
    raw = read_saif(work / 'gate/activity.saif')
    window = dict(line.split('=') for line in (work / 'gate/window.txt').read_text().splitlines())
    if int(window['end_fs']) - int(window['start_fs']) != 512000000:
        raise ValueError('Captured window differs')
    aliases = expand_leaf_aliases(raw, netlist, point['top'], scopes, scope)
    save(work / 'saif_aliases.json', aliases)
    write_saif(work / 'activity.saif', raw)
    audit, parsed = audit_saif(work / 'activity.saif', scopes, 512000000, scope)
    # The upstream audit checks vectors by base name; require every declared top bit too.
    text = netlist.read_text()
    top_body = re.search(r'\bmodule\s+' + re.escape(point['top']) + r'\s*\(.*?\);(.*?)endmodule', text, re.S)[1]
    for width, names in re.findall(r'\b(?:input|output)\s*(\[[^]]+\])?\s*([^;]+);', top_body):
        ports = [name.strip() for name in names.split(',')]
        indices = [None]
        if width:
            hi, lo = map(int, re.findall(r'\d+', width))
            indices = range(min(hi, lo), max(hi, lo) + 1)
        for name in ports:
            for index in indices:
                pin = scope + '/' + name + (f'[{index}]' if index is not None else '')
                if pin not in parsed['signals'] or parsed['signals'][pin].get('TX', 0) or parsed['signals'][pin].get('TZ', 0):
                    raise ValueError('Missing/unknown top port bit: ' + pin)
    for source, target in [('gate/activity.saif', 'native.saif.gz'), ('activity.saif', 'activity.saif.gz')]:
        with (work / source).open('rb') as inp, gzip.open(work / target, 'wb') as out:
            shutil.copyfileobj(inp, out)
    save(work / 'saif_audit.json', audit | window)
    resolved = gate['resolved']
    clock_slew = resolved['constraints']['clock_transition_ns']
    parameters = dict(ddc=ROOT / point['artifacts']['ddc']['path'], top=point['top'], scope=scope,
                      saif_file=work / 'activity.saif.gz', clock_name='clock', clock_slew_ns=clock_slew)
    config = '\n'.join('set ' + name + ' ' + tcl(value) for name, value in parameters.items())
    config += '\nset databases [list ' + ' '.join(tcl(path) for path in resolved['target_dbs']) + ']\n'
    (work / 'config.tcl').write_text(config)
    shutil.copyfile(POWER / 'tcl/power.tcl', work / 'power.tcl')
    execute([machine['dc_shell'], '-f', str(work / 'power.tcl')], work,
            work / 'power_compiler.log', machine['setup_script'])
    log = (work / 'power_compiler.log').read_text()
    if 'DP_POWER_COMPILER_PASS' not in log or re.search(r'^Error:', log, re.M):
        raise ValueError('Power Compiler did not complete cleanly')
    counts = {}
    annotation = (work / 'activity.rpt').read_text()
    for kind in ('Nets', 'Ports', 'Pins'):
        match = re.search(r'^\s*' + kind + r'\s+(\d+)\(100\.00%\)\s+0\(0\.00%\)\s+0\(0\.00%\)\s+(\d+)', annotation, re.M)
        if not match or match[1] != match[2]:
            raise ValueError('Activity annotation is not 100% explicit: ' + kind)
        counts[kind] = int(match[1])
    pins = pin_activities(work / 'pin_activity.rpt')
    clocks = pin_activities(work / 'clock_activity.rpt')
    expected_pins = {instance[len(scope)+1:] + '/' + pin for instance, names in scopes.items()
                     if instance != scope for pin in names}
    if set(pins) != expected_pins or len(pins) != counts['Pins']:
        raise ValueError('Power Compiler pin inventory differs from mapped netlist')
    for name, activity in (pins | clocks).items():
        value = parsed['signals'].get(scope + '/' + name)
        if value is None or activity['origin'] != 'simulated':
            raise ValueError('Activity did not come from SAIF: ' + name)
        if (not math.isclose(value['TC'] / 512e-9, activity['density_per_second'], rel_tol=1e-4, abs_tol=1e-4)
                or abs(value['T1'] / parsed['duration_ticks'] - activity['duty']) > 1e-5):
            raise ValueError('Pin probability/density mismatch: ' + name)
    transitions = {}
    for line in (work / 'clock_transitions.rpt').read_text().splitlines():
        match = re.match(r'^(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', line)
        if match:
            transitions[match[1]] = list(map(float, match.groups()[1:]))
    if set(transitions) != set(clocks) or any(abs(value-clock_slew) > 1e-5 for row in transitions.values() for value in row):
        raise ValueError('Clock transition audit failed')
    power = parse_power((work / 'power.rpt').read_text())
    result = dict(status='PASS', top=point['top'], format=point['format'], logical_k=point['logical_k'],
                  dc_run=point['dc_run'], export_id=point['export_id'],
                  technology=resolved['technology'], frequency_hz=1e9, duration_ns=512,
                  area_um2=json.loads((ROOT / point['dc_run'] / 'summary.json').read_text())['area']['total_cell_area_um2'],
                  internal_mw=power['internal']*1000, switching_mw=power['switching']*1000,
                  dynamic_mw=(power['internal']+power['switching'])*1000,
                  static_mw=power['leakage']*1000, total_mw=power['total']*1000,
                  pj_per_mac=power['total']/point['logical_k']*1000,
                  annotated_pins=len(pins), annotation=counts, clock_pins=len(clocks),
                  inactive_clock_pins=sum(row['density_per_second'] == 0 for row in clocks.values()),
                  saif_audit=audit, alias_count=len(aliases), clock_slew_ns=clock_slew,
                  finished_utc=now())
    result['artifacts_sha256'] = {str(path.relative_to(ROOT)): digest(path) for path in
                                  [work / name for name in ('native.saif.gz', 'activity.saif.gz',
                                   'power.rpt', 'hierarchy_power.rpt', 'activity.rpt', 'pin_activity.rpt',
                                   'clock_activity.rpt', 'clock_transitions.rpt', 'saif_audit.json',
                                   'rtl/results.txt', 'gate/results.txt', 'rtl/simulation.log', 'gate/simulation.log')]}
    save(work / 'power_audit.json', result)
    # Only disposable plain files from this successful run; both compressed forms retained.
    (work / 'gate/activity.saif').unlink()
    (work / 'activity.saif').unlink()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=POWER / 'plans/qwen3_8b_first3.json')
    parser.add_argument('--machine', type=Path, default=POWER / 'configs/machine.local.json')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--max-points', type=int, default=15)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'power_[A-Za-z0-9_]+', args.run_id):
        parser.error('Use a safe explicit power_<name> run ID')
    dependencies()
    campaign = POWER / 'runs' / args.run_id
    if campaign.exists() and not args.resume:
        parser.error('Run exists; explicit --resume required')
    campaign.mkdir(parents=True, exist_ok=True)
    plan = json.loads(args.plan.read_text())
    if (campaign / 'plan.json').exists() and json.loads((campaign / 'plan.json').read_text()) != plan:
        raise ValueError('Cannot resume with a changed plan')
    save(campaign / 'plan.json', plan)
    machine = json.loads(args.machine.read_text())
    probe = subprocess.run(['bash', '-c', 'source ' + shlex.quote(machine['setup_script']) +
                            ' >/dev/null 2>&1\ncommand -v vcs'], capture_output=True, text=True, check=True)
    machine['vcs'] = probe.stdout.strip()
    for name in ('vcs', 'dc_shell', 'iverilog', 'vvp'):
        if not Path(machine[name]).is_file():
            raise ValueError('Missing tool: ' + name)
    machine['cell_models_sha256'] = {path: digest(path) for path in machine['cell_models']}
    save(campaign / 'machine.local.json', machine)
    execute([machine['iverilog'], '-V'], campaign, campaign / 'iverilog_version.log')
    version = (campaign / 'iverilog_version.log').read_text().splitlines()[1]
    (campaign / '.running').write_text(now())
    evidence = [Path(__file__), ROOT / 'scripts/dp_power_gate.py', ROOT / 'scripts/rtl_gate.py',
                POWER / 'tb/dp_power_tb.sv.in', POWER / 'tcl/power.tcl',
                ROOT / 'dependencies/petile-power.json']
    manifest = dict(plan_sha256=digest(args.plan), dc_runs=sorted({p['dc_run'] for p in plan['points']}),
                    flow_sources_sha256={str(p.relative_to(ROOT)): digest(p) for p in evidence},
                    cell_models_sha256=list(machine['cell_models_sha256'].values()))
    if (campaign / 'manifest.json').exists() and json.loads((campaign / 'manifest.json').read_text()) != manifest:
        raise ValueError('Cannot resume with changed flow/model provenance')
    save(campaign / 'manifest.json', manifest)
    for path in evidence:
        archived = campaign / 'provenance' / path.relative_to(ROOT)
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, archived)
    state = dict(status='running', phase='running', started_utc=now(), points=[])
    save(campaign / 'state.json', state)
    try:
        for point in plan['points'][:args.max_points]:
            name = point['top'] + '__' + point['format']
            work = campaign / name
            if (work / 'power_audit.json').exists():
                audit = json.loads((work / 'power_audit.json').read_text())
                for path, expected in audit['artifacts_sha256'].items():
                    if digest(ROOT / path) != expected:
                        raise ValueError('Completed power evidence changed')
                check_data(point)
                frozen_dc_source(ROOT, point)
                state['points'].append(dict(point=name, status='PASS', reused=True))
                continue
            if work.exists():
                raise ValueError('Incomplete point retained; use a new run ID: ' + name)
            work.mkdir()
            save(work / 'point.json', point)
            print('START ' + name, flush=True)
            gate = frozen_dc_source(ROOT, point)
            build, compiled, groups = compile_design(campaign, work, point, gate, machine)
            count = prepare_vectors(point, work, groups)
            execute([machine['vvp'], str(build / 'rtl.vvp')], work / 'rtl', work / 'rtl/simulation.log')
            check_simulation(work, work / 'rtl', count)
            receipt = replay_receipt(point, work, gate, compiled, count, version)
            verify_power_input(point, receipt, ROOT)
            print('RTL_PASS ' + name, flush=True)
            execute([str(build / 'simv'), '-no_save'], work / 'gate', work / 'gate/simulation.log', machine['setup_script'])
            check_simulation(work, work / 'gate', count, saif=True)
            verify_power_input(point, receipt, ROOT)
            print('GLS_SAIF_PASS ' + name, flush=True)
            result = measure(point, work, gate, machine)
            state['points'].append(dict(point=name, status='PASS'))
            save(campaign / 'state.json', state)
            print(f'POWER_PASS {name} dynamic={result["dynamic_mw"]:.6f}mW static={result["static_mw"]:.6f}mW', flush=True)
        finish_state(state, 'completed' if len(state['points']) == len(plan['points']) else 'partial')
    except Exception as error:
        finish_state(state, 'failed')
        state['error'] = str(error)
        raise
    finally:
        save(campaign / 'state.json', state)
        (campaign / '.running').unlink()


if __name__ == '__main__':
    main()
