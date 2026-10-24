#!/usr/bin/env python3
"""Inspect an explicit six-profile export; optional directed unit-value/layout/latency RTL smoke.

This is not complete format accuracy verification and never sets passed/PPA eligibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {'PE_HQE_g4', 'PE_QE_g4', 'PE_H_g4', 'PE_Q_g4', 'PE_E_g4', 'PE_E_g2'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(export_id):
    require(Path(export_id).name == export_id, 'Expected explicit export ID')
    directory = ROOT / 'hw/rtl' / export_id
    manifest = json.loads((directory / 'manifest.json').read_text())
    require(manifest['export_id'] == export_id and manifest['state'] == 'generated', 'Expected generated export')
    require(manifest['validation'] == {'rtl_test': 'not_run', 'ppa_eligible': False}, 'Unexpected validation state')
    config = manifest['parameters']
    require(config['schema_version'] == 2 and all(p in PROFILES for p in config['layout']), 'Unexpected profiles')
    source_text = '\n'.join(f"{x['path']} {x['sha256']}" for x in manifest['sources'])
    require(digest(source_text.encode()) == manifest['source_sha256'], 'Source inventory mismatch')
    listed = {}
    for item in manifest['files']:
        relative = Path(item['path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Invalid input path')
        data = (directory / relative).read_bytes()
        require(digest(data) == item['sha256'], 'RTL/input hash mismatch: ' + item['path'])
        listed[item['path']] = data
    filelist = (directory / 'files.f').read_bytes()
    require(digest(filelist) == manifest['filelist_sha256'], 'files.f mismatch')
    paths = [p for p in filelist.decode().splitlines() if not p.startswith('+incdir+')]
    require(len(paths) == len(set(paths)) and set(paths) == {p for p in listed if p.endswith('.sv')}, 'Filelist mismatch')
    modules = {}
    for item in manifest['modules']:
        data = listed[item['path']]
        require(digest(data) == item['sha256'], 'Module hash mismatch')
        names = re.findall(r'^\s*module\s+(\w+)\b', data.decode(), re.M)
        require(names == [item['module']] and Path(item['path']).stem == names[0], 'Expected one same-named module')
        require(names[0] not in modules, 'Duplicate module')
        require((ROOT / item['chisel_source']).is_file(), 'Missing source mapping')
        modules[names[0]] = data.decode()

    def instances(module, prefix):
        return re.findall(r'^\s*(' + re.escape(prefix) + r'\w*)\s+(\w+)\s*\(', modules[module], re.M)

    top = manifest['top']
    require(top in modules, 'Missing top')
    pe_instances = [(top, top)] if config['top'] == 'pe' else instances(top, 'PE_')
    require(len(pe_instances) == len(config['layout']), 'PE instance count mismatch')
    total_groups = total_subs = 0
    for pe_type, _ in pe_instances:
        match = re.match(r'PE_(HQE|QE|H|Q|E)_g([24])', pe_type)
        require(match is not None, 'Unexpected PE type')
        family, count = match.group(1), int(match.group(2))
        groups = instances(pe_type, 'PEGroup_' + family)
        require(len(groups) == count, 'PG instance count mismatch')
        for group, _ in groups:
            require(len(instances(group, 'SubPE_' + family)) == 4, 'SubPE count mismatch')
        if family in ('H', 'Q'):
            require(len(instances(pe_type, 'PEGlobalAlignNormalize_' + family)) == 1, 'Missing global H/Q alignment')
            require(not instances(pe_type, 'PEAlignNormalize'), 'H/Q still contains staged PG reduction')
        else:
            require(len(instances(pe_type, 'PEAlignNormalize')) == 1, 'Missing preserved staged reduction')
        total_groups += count
        total_subs += count * 4
    if config['top'] == 'pe':
        port_map = ports(modules[top])
        require(port_map['io_out_data_bits_magnitude'][1] == config['alignment']['pe_align_width'] + 1,
                'PE output fraction window does not match effective config')
        require(port_map['io_out_data_bits_top_anchor'][1] == 11, 'PE anchor width mismatch')
    else:
        operand = re.search(r'reg\s+\[(\d+):0\]\s+s13_terms_q_0\b', modules[top])
        summed = re.search(r'reg\s+\[(\d+):0\]\s+s14_sum_q\b', modules[top])
        expected = config['alignment']['top_align_width'] + 2
        require(operand is not None and int(operand.group(1)) + 1 == expected, 'K/MN top window propagation mismatch')
        require(summed is not None and int(summed.group(1)) + 1 == expected + len(config['layout']).bit_length(),
                'K/MN natural sum growth mismatch')
        for helper in ('CUnpacker', 'LzdNormalize', 'RoundPack'):
            require(len(instances(top, helper)) == 1, 'C/D helper must be shared exactly once: ' + helper)
    report = {'export_id': export_id, 'source_sha256': manifest['source_sha256'],
              'alignment': config['alignment'], 'physical_instances': {
                  'PE': len(pe_instances), 'PEGroup': total_groups, 'SubPE': total_subs},
              'module_definitions': len(modules), 'full_rtl_accuracy': 'not_run', 'ppa_eligible': False}
    return directory, manifest, modules, report


def ports(text):
    start = re.search(r'^\s*module\s+\w+\s*\(', text, re.M).end()
    header = text[start:text.index(');', start)]
    header = re.sub(r'//[^\n]*', '', header)
    result = {}
    direction, width = None, 1
    for segment in header.split(','):
        segment = segment.strip()
        match = re.match(r'(input|output)\s+(?:wire\s+|reg\s+)?(?:signed\s+)?(?:\[(\d+):0\]\s*)?(\w+)$', segment)
        if match:
            direction, high, name = match.groups()
            width = int(high) + 1 if high else 1
        else:
            match = re.fullmatch(r'(\w+)', segment)
            require(match is not None and direction is not None, 'Unrecognized port: ' + segment)
            name = match.group(1)
        result[name] = direction, width
    return result


def smoke(directory, manifest, modules):
    config = manifest['parameters']
    require(config['top'] == 'pe', 'Directed smoke currently covers standalone base PEs')
    family = config['layout'][0].split('_')[1]
    group_count = int(config['layout'][0][-1])
    fbits = config['alignment']['pe_align_width']
    port_map = ports(modules[manifest['top']])
    declarations = []
    for name, (direction, width) in port_map.items():
        declarations.append(f"{'reg' if direction == 'input' else 'wire'} [{width-1}:0] {name};")
    connect = ',\n'.join('.' + n + '(' + n + ')' for n in port_map)
    body = ['module tb;', *declarations, f"{manifest['top']} dut({connect});", 'always #5 clock = ~clock;',
            'integer valid_pipe[0:10]; integer sum_pipe[0:10]; integer input_sum; integer checks = 0; integer i;',
            'reg [127:0] expected_magnitude; integer expected_anchor; integer abs_sum;',
            'always @(posedge clock) begin',
            '  if (reset) begin for (i=0;i<11;i=i+1) begin valid_pipe[i]=0; sum_pipe[i]=0; end end',
            '  else begin',
            '    for(i=10;i>0;i=i-1) begin valid_pipe[i]=valid_pipe[i-1]; sum_pipe[i]=sum_pipe[i-1]; end',
            '    valid_pipe[0]=io_in_data_valid; sum_pipe[0]=input_sum;',
            '    #1;',
            '    if(io_out_data_valid !== valid_pipe[10][0]) $fatal(1,"11-stage valid mismatch");',
            '    if(valid_pipe[10]) begin',
            '      abs_sum = sum_pipe[10] < 0 ? -sum_pipe[10] : sum_pipe[10];',
            '      expected_anchor = -1024; expected_magnitude=0;',
            '      if(abs_sum != 0) begin',
            '        expected_anchor=0; for(i=0;i<31;i=i+1) if((abs_sum >> i)!=0) expected_anchor=i;',
            f'        expected_magnitude=abs_sum; expected_magnitude=expected_magnitude << ({fbits}-expected_anchor);',
            '      end',
            '      if(io_out_data_bits_magnitude !== expected_magnitude) $fatal(1,"magnitude mismatch got=%h expected=%h sum=%d",io_out_data_bits_magnitude,expected_magnitude,sum_pipe[10]);',
            '      if($signed(io_out_data_bits_top_anchor) !== expected_anchor) $fatal(1,"anchor mismatch");',
            '      if(io_out_data_bits_negative !== (sum_pipe[10]<0)) $fatal(1,"sign mismatch");',
            '      if(io_out_data_bits_is_zero !== (sum_pipe[10]==0)) $fatal(1,"zero mismatch");',
            '      if(io_out_data_bits_special_is_nan || io_out_data_bits_special_is_pos_inf || io_out_data_bits_special_is_neg_inf) $fatal(1,"unexpected special");',
            '      checks=checks+1;', '    end', '  end', 'end', 'initial begin']
    for name, (direction, _) in port_map.items():
        if direction == 'input':
            body.append(name + '=0;')
    body += ['input_sum=0; reset=1; repeat(3) @(negedge clock); reset=0;']
    # (dtype, scale type, scale-one code, element-one code, sign bit, storage bits)
    all_modes = {'H': [(8, 0, 127, 0x3c00, 15, 16), (7, 0, 127, 0x3f80, 15, 16)],
                 'Q': [(6, 2, 127, 0x3c, 7, 8), (5, 2, 127, 0x38, 7, 8),
                       (4, 2, 127, 0xc, 5, 8), (3, 2, 127, 8, 5, 8)],
                 'E': [(1, 2, 127, 2, 3, 4), (0, 1, 0x38, 2, 3, 4), (2, 3, 0xc0, 4, 3, 4)]}
    modes = sum((all_modes[k] for k in 'HQE' if k in family), [])
    samples = 0
    for mode_index, (dtype, sf_type, scale_one, one, sign_bit, storage_bits) in enumerate(modes):
        lanes_per_word = 16 // storage_bits
        lanes = group_count * 4 * lanes_per_word
        body += ['@(negedge clock); io_in_data_valid=0;', f'io_in_cfg_data_type={dtype}; io_in_cfg_b_data_type={dtype};',
                 f'io_in_cfg_sf_type={sf_type}; io_in_cfg_b_sf_type={sf_type};']
        for name, (direction, _) in port_map.items():
            if direction != 'input':
                continue
            if re.fullmatch(r'io_in_data_bits_[ab]_data_type', name):
                body.append(f'{name}={dtype};')
            if name.endswith('_sf_sf_type'):
                body.append(f'{name}={sf_type};')
            if re.search(r'_sf_sf_data_\d+$', name):
                body.append(f'{name}={scale_one};')
        for sample in range(20):
            rng = random.Random(0x5eed + mode_index * 100 + sample)
            a = [rng.choice([-1, 0, 1]) for _ in range(lanes)]
            b = [rng.choice([-1, 0, 1]) for _ in range(lanes)]
            if sample == 0:
                a, b = [1] * lanes, [1] * lanes
            if sample == 1:
                a, b = [-1] * lanes, [1] * lanes
            if sample == 2:
                a = [0] * lanes
            if family == 'E' and group_count == 4 and sample >= 10:
                a[32:] = [0] * (lanes - 32)
            valid = sample % 5 != 4
            body.append(f'@(negedge clock); io_in_data_valid={int(valid)}; input_sum={sum(x*y for x,y in zip(a,b))};')
            for operand, values in [('a', a), ('b', b)]:
                for word in range(group_count * 4):
                    packed = 0
                    for slot in range(lanes_per_word):
                        value = values[word * lanes_per_word + slot]
                        code = 0 if value == 0 else one | ((1 << sign_bit) if value < 0 else 0)
                        packed |= code << (slot * storage_bits)
                    body.append(f"io_in_data_bits_{operand}_data_{word}=16'h{packed:04x};")
            samples += int(valid)
        body += ['@(negedge clock); io_in_data_valid=0; repeat(13) @(negedge clock);']
    body += [f'if(checks!={samples}) $fatal(1,"missing outputs");',
             '$display("DIRECTED_LAYOUT_LATENCY_SMOKE checks=%0d",checks); $finish;', 'end',
             'initial begin #100000; $fatal(1,"timeout"); end', 'endmodule']
    run = ROOT / 'hw/test/runs' / ('six-pe-' + directory.name)
    run.mkdir(parents=True, exist_ok=True)
    tb = run / 'tb.sv'
    tb.write_text('\n'.join(body) + '\n')
    commands = [['iverilog', '-g2012', '-s', 'tb', '-o', str(run / 'sim.vvp'), '-f', 'files.f', str(tb)],
                ['vvp', str(run / 'sim.vvp')]]
    logs = []
    for command in commands:
        result = subprocess.run(command, cwd=directory, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        logs.append(result.stdout)
        (run / 'smoke.log').write_text('\n'.join(logs))
        require(result.returncode == 0, 'Directed smoke failed; see ' + str(run / 'smoke.log'))
    (run / 'sim.vvp').unlink()
    return {'kind': 'directed_unit_values_layout_and_11_stage_valid', 'checks': samples,
            'seed': '0x5eed', 'full_format_accuracy': 'not_run', 'ppa_eligible': False,
            'testbench_sha256': digest(tb.read_bytes()), 'checker_sha256': digest(Path(__file__).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export_id')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    directory, manifest, modules, report = inspect(args.export_id)
    if args.smoke:
        report['directed_smoke'] = smoke(directory, manifest, modules)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
