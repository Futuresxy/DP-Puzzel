#!/usr/bin/env python3
"""Compare two explicit canonical exports cycle by cycle; not an accuracy oracle.

Separate Icarus simulations consume the same packed stimulus, so neither RTL
input needs copying, renaming, or patching. Valid/last latency is also checked
independently (PE: 11 register boundaries; K/MN: 18).
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from check_pe_export import ports, require

ROOT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_export(export_id):
    require(Path(export_id).name == export_id, 'Expected an explicit export ID')
    directory = ROOT / 'hw/rtl' / export_id
    manifest = json.loads((directory / 'manifest.json').read_text())
    require(manifest['export_id'] == export_id and manifest['state'] == 'generated', 'Expected generated export')
    inventory = '\n'.join(f"{item['path']} {item['sha256']}" for item in manifest['sources'])
    require(sha256(inventory.encode()) == manifest['source_sha256'], 'Source inventory mismatch')
    listed = {}
    for item in manifest['files']:
        relative = Path(item['path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe RTL path')
        data = (directory / relative).read_bytes()
        require(sha256(data) == item['sha256'], 'Input hash mismatch: ' + item['path'])
        listed[item['path']] = data
    filelist = (directory / 'files.f').read_bytes()
    require(sha256(filelist) == manifest['filelist_sha256'], 'Filelist hash mismatch')
    paths = [line for line in filelist.decode().splitlines() if not line.startswith('+incdir+')]
    require(len(paths) == len(set(paths)) and set(paths) == {p for p in listed if p.endswith('.sv')},
            'Filelist/inventory mismatch')
    top = next(item for item in manifest['modules'] if item['module'] == manifest['top'])
    return directory, manifest, ports(listed[top['path']].decode())


def pairs_for(layout):
    capabilities = {'H': {8, 7}, 'Q': {6, 5, 4, 3}, 'E': {1, 0, 2}}
    pairs = [(8, 8), (7, 7)] + [(a, b) for a in (6, 5, 4, 3) for b in (6, 5, 4, 3)]
    pairs += [(a, b) for a in (1, 0) for b in (1, 0)] + [(2, 2)]
    supported = [set().union(*(capabilities[c] for c in p.split('_')[1])) for p in layout]
    return [(a, b) for a, b in pairs if any(a in formats and b in formats for formats in supported)]


def stimuli(manifest, port_map, seed, samples):
    core = manifest['parameters']['top'] != 'pe'
    cfg_prefix = 'io_in_cfg_bits_' if core else 'io_in_cfg_'
    operand_prefix = 'io_in_ab_bits_' if core else 'io_in_data_bits_'
    inputs = [(name, width) for name, (direction, width) in port_map.items() if direction == 'input' and name != 'clock']
    row = {name: 0 for name, _ in inputs}
    rows = []
    rng = random.Random(seed)

    def idle(reset=0, cycles=1):
        row['reset'] = reset
        for name in ('io_in_cfg_valid', 'io_in_ab_valid', 'io_in_c_valid', 'io_in_data_valid'):
            if name in row:
                row[name] = 0
        for _ in range(cycles):
            rows.append(row.copy())

    def configure():
        idle()
        if core:
            row['io_in_cfg_valid'] = 1
            rows.append(row.copy())
            idle()

    idle(reset=1, cycles=3)
    pairs = pairs_for(manifest['parameters']['layout'])
    for batch, (a_type, b_type) in enumerate(pairs):
        sf_types = [0 if t in (8, 7) else 1 if t == 0 else 3 if t == 2 else 2 for t in (a_type, b_type)]
        row[cfg_prefix + 'data_type'] = a_type
        row[cfg_prefix + 'b_data_type'] = b_type
        row[cfg_prefix + 'sf_type'], row[cfg_prefix + 'b_sf_type'] = sf_types
        row[cfg_prefix + 'c_type'] = batch % 3
        row[cfg_prefix + 'out_type'] = 0
        row[cfg_prefix + 'rm'] = batch % 5
        configure()
        for sample in range(samples):
            # Flush in-flight work with reset, then resume a fresh core batch.
            if sample == samples // 3:
                idle(reset=1, cycles=2)
                configure()
            for name, width in inputs:
                if name.startswith(operand_prefix):
                    value = rng.getrandbits(width)
                    if '_data_' in name and not name.endswith('_data_type'):
                        if sample == 0:
                            value = 0
                        elif sample == 1:
                            value = (1 << width) - 1
                        elif sample % 4 == 0:
                            value = rng.choice([1, 0x8000, 0x7c00, 0x7f80, 0x7fff, 0x3c3c, 0x3838, 0x080c, 0x1234])
                    if '_sf_sf_data_' in name and sample % 3 == 0:
                        value = rng.choice([0, 1, 0x38, 0x7e, 0x7f, 0x80, 0xc0, 0xfe, 0xff])
                    row[name] = value & ((1 << width) - 1)
            if core:
                # Core payload tags are checked at admission, unlike PE input tags.
                for side, data_type, sf_type in zip(('a', 'b'), (a_type, b_type), sf_types):
                    row[operand_prefix + side + '_data_type'] = data_type
                    row[operand_prefix + side + '_sf_sf_type'] = sf_type
                row['io_in_ab_valid'] = int(sample % 7 != 4 or sample == samples - 1)
                row['io_in_c_valid'] = int(sample % 5 != 3 or sample == samples - 1)
                row['io_in_ab_bits_last'] = int(sample == samples - 1)
                row['io_in_c_bits_c'] = rng.getrandbits(32)
            else:
                row['io_in_data_valid'] = int(sample % 5 != 3 or sample == samples - 1)
            rows.append(row.copy())
        idle(cycles=22)
    idle(cycles=22)
    packed = []
    for values in rows:
        word = 0
        for name, width in inputs:
            word = (word << width) | values[name]
        packed.append(f'{word:x}')
    return inputs, packed, pairs


def testbench(manifest, port_map, inputs, count, stimulus_path):
    core = manifest['parameters']['top'] != 'pe'
    latency = 18 if core else 11
    out_valid = 'io_out_result_valid' if core else 'io_out_data_valid'
    admitted = '(io_in_ab_valid && io_in_ab_ready && io_in_c_valid && io_in_c_ready)' if core else 'io_in_data_valid'
    last = 'io_in_ab_bits_last' if core else "1'b0"
    payload = [n for n, (d, _) in port_map.items() if d == 'output' and '_bits_' in n]
    controls = [n for n, (d, _) in port_map.items() if d == 'output' and '_bits_' not in n]
    declarations = [f"{'reg' if d == 'input' else 'wire'} [{w-1}:0] {n};" for n, (d, w) in port_map.items()]
    body = ['module tb;', *declarations,
            manifest['top'] + ' dut(' + ','.join(f'.{n}({n})' for n in port_map) + ');',
            'always #5 clock=~clock;',
            f'reg [{sum(w for _, w in inputs)-1}:0] stimulus [0:{count-1}];',
            f'reg [{latency-1}:0] valid_pipe=0, last_pipe=0;',
            'integer row_index; integer cycle=0; integer checks=0; reg running=0;',
            'always @(posedge clock) if(running) begin',
            '  if(reset) begin valid_pipe=0; last_pipe=0; end else begin',
            f'    valid_pipe={{valid_pipe[{latency-2}:0],{admitted}}};',
            f'    last_pipe={{last_pipe[{latency-2}:0],{last}}};',
            '  end', '  #1;',
            f'  if({out_valid} !== valid_pipe[{latency-1}]) $fatal(1,"fixed latency mismatch cycle=%0d",cycle);']
    if core:
        body += [f'  if({out_valid} && io_out_result_bits_last !== last_pipe[{latency-1}]) $fatal(1,"last latency mismatch");']
    body += ['  $write("TRACE %0d",cycle);',
             '  $write("' + ' %h' * len(controls) + '",' + ','.join(controls) + ');',
             f'  if({out_valid}) begin',
             '    $write("' + ' %h' * len(payload) + '",' + ','.join(payload) + ');',
             '    checks=checks+1; end', '  $write("\\n"); cycle=cycle+1;', 'end', 'initial begin']
    body += [f'{n}=0;' for n, (d, _) in port_map.items() if d == 'input']
    body += [f'$readmemh("{stimulus_path}",stimulus);', f'for(row_index=0;row_index<{count};row_index=row_index+1) begin',
             '@(negedge clock); {' + ','.join(n for n, _ in inputs) + '}=stimulus[row_index]; running=1;',
             'end', '@(negedge clock); if(checks==0) $fatal(1,"no results checked");',
             '$display("CHECKS %0d",checks); $finish;', 'end', 'endmodule']
    return '\n'.join(body) + '\n'


def simulate(directory, manifest, tb, run):
    run.mkdir()
    commands = [['iverilog', '-g2012', '-s', 'tb', '-o', str(run / 'sim.vvp'), '-f', 'files.f', str(tb)],
                ['vvp', str(run / 'sim.vvp')]]
    for label, command in zip(('compile', 'simulation'), commands):
        result = subprocess.run(command, cwd=directory, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (run / (label + '.log')).write_text(result.stdout)
        require(result.returncode == 0, f'{manifest["export_id"]} {label} failed; see {run}')
    (run / 'sim.vvp').unlink()
    traces = [line for line in result.stdout.splitlines() if line.startswith('TRACE ')]
    require(traces and all(not re.search(r'[xz]', line, re.I) for line in traces), 'Unknown valid output/control')
    count = int(re.search(r'CHECKS (\d+)', result.stdout).group(1))
    return traces, count, commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline')
    parser.add_argument('candidate')
    parser.add_argument('--seed', type=lambda s: int(s, 0), default=0x5eed27)
    parser.add_argument('--samples', type=int, default=64)
    args = parser.parse_args()
    require(args.samples >= 12, 'Use at least 12 samples per format pair')
    before, old_manifest, old_ports = load_export(args.baseline)
    after, new_manifest, new_ports = load_export(args.candidate)
    require(old_manifest['parameters'] == new_manifest['parameters'], 'Different effective parameters')
    require(old_manifest['top'] == new_manifest['top'] and old_ports == new_ports, 'Changed public interface')
    run = ROOT / 'hw/test/runs' / ('pe-locality-' + args.baseline + '-vs-' + args.candidate)
    run.mkdir(parents=True, exist_ok=False)
    inputs, packed, pairs = stimuli(new_manifest, new_ports, args.seed, args.samples)
    stimulus = run / 'stimulus.mem'
    stimulus.write_text('\n'.join(packed) + '\n')
    tb = run / 'tb.sv'
    tb.write_text(testbench(new_manifest, new_ports, inputs, len(packed), stimulus))
    old_trace, old_count, old_commands = simulate(before, old_manifest, tb, run / 'baseline')
    new_trace, new_count, new_commands = simulate(after, new_manifest, tb, run / 'candidate')
    require(old_trace == new_trace and old_count == new_count, 'Cycle-by-cycle output/control mismatch')
    report = dict(scope='sampled_refactor_equivalence_and_fixed_latency', baseline=args.baseline,
                  candidate=args.candidate, source_before=old_manifest['source_sha256'],
                  source_after=new_manifest['source_sha256'], seed=hex(args.seed), samples_per_pair=args.samples,
                  format_pairs=pairs, cycles=len(new_trace), valid_results=new_count, result='passed',
                  latency=11 if new_manifest['parameters']['top'] == 'pe' else 18,
                  full_format_accuracy='not_run', ppa_eligible=False,
                  stimulus_sha256=sha256(stimulus.read_bytes()), testbench_sha256=sha256(tb.read_bytes()),
                  checker_sha256=sha256(Path(__file__).read_bytes()), trace_sha256=sha256('\n'.join(new_trace).encode()),
                  commands=old_commands + new_commands)
    (run / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
