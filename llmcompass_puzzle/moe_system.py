"""Analytical EP MoE-prefill system, using pinned LLMCompass hardware costs.

Boundary: one MoE sublayer; all MoE-layer weights resident. Not full-model TTFT.
"""
import math
from collections import Counter

from ratio_dse.common import identity, require
from ratio_dse.formats import layout, vector_bytes
from .backend import baseline_config, vector_bundle
from .characterize import substitute_tensor
from .system_contract import quantization_work

Q, E = 'mxfp8_e4m3', 'mxfp4_e2m1'


def packed(rows, columns, fmt):
    if fmt == 'bf16':
        return rows * columns * 2
    payload, scales = vector_bytes(columns, layout(fmt))
    return rows * (payload + scales) + (4 if fmt == 'nvfp4' else 0)


def make_design(profile, physical_sms, vector, hbm, l2, settings):
    c = vector_bundle(baseline_config(clock_hz=profile['frequency_hz']), vector)
    chip, io = c['device']['compute_chiplet'], c['device']['io']
    chip['physical_core_count'] = physical_sms
    chip['core_count'] = physical_sms * 108 // 128
    io.update(memory_channel_physical_count=hbm['physical_channels'], memory_channel_active_count=hbm['active_channels'],
              physical_global_buffer_MB=l2['physical_mib'], global_buffer_MB=l2['enabled_mib'])
    area = substitute_tensor(c, profile, (4, 4), settings['extra_tensor_mm2_per_sm'])
    return {'design_id': identity('system', [profile['profile_id'], physical_sms, vector, hbm, l2]),
            'ratio': profile['ratio_label'], 'profile_id': profile['profile_id'], 'physical_sms': physical_sms,
            'enabled_sms': chip['core_count'], 'vector_scale': vector, 'area_mm2': area['area_model_total_mm2'],
            'hbm_id': hbm['id'], 'hbm_capacity_bytes': hbm['capacity_gb'] * 10**9,
            'hbm_bytes_s': hbm['active_channels'] * settings['hbm_bytes_s_per_channel'],
            'hbm_physical_channels': hbm['physical_channels'], 'l2_id': l2['id'],
            'l2_bytes': l2['enabled_mib'] * 1024**2, 'l2_bytes_s': l2['bytes_cycle'] * profile['frequency_hz'],
            'sram_bytes': settings['usable_sram_kib'] * 1024, 'clock_hz': profile['frequency_hz'],
            'vector_work_s_per_sm': 128 * vector * profile['frequency_hz'],
            'link_bytes_s': settings['link_bytes_s'], 'link_latency_s': settings['link_latency_s']}


def resident_bytes(model, plan, devices, reserved_bytes):
    # All routed experts, not just activated experts; non-MoE reservation is explicit.
    d, f = model['dim'], model['moe_inter_dim']
    wfmt = 'nvfp4' if plan == 'routed_nvfp4' else E
    per_expert = 2 * packed(f, d, wfmt) + packed(d, f, wfmt)
    shared = model['n_shared_experts'] * (2 * packed(f, d, Q) + packed(d, f, Q))
    return model['n_layers'] * (math.ceil(model['n_routed_experts'] / devices) * per_expert + shared) + reserved_bytes


def routing(model, tokens, devices, policy):
    experts, topk = model['n_routed_experts'], model['n_activated_experts']
    require(experts % devices == 0 and tokens % devices == 0, 'equal EP rank partition required')
    if policy == 'balanced':
        q, r = divmod(tokens * topk, experts)
        counts = [q + (i < r) for i in range(experts)]
    elif policy == 'hot':
        counts = [tokens if i < topk else 0 for i in range(experts)]
    else:
        raise ValueError('unsupported routing policy')
    # Contiguous expert ownership; analyze each rank, never average a hot expert away.
    n = experts // devices
    return [Counter(x for x in counts[r*n:(r+1)*n] if x) for r in range(devices)]


def base_power(design, p):
    return (p['fixed_w'] + design['physical_sms'] * p['idle_w_per_sm']
            + design['hbm_physical_channels'] * p['hbm_idle_w_per_channel']
            + design['l2_bytes'] / 1024**2 * p['l2_idle_w_per_mib'])


def vector_stage(name, work, special, read_bytes, write_bytes, working_bytes, design, settings, power, cap,
                 cold=False, launch=True):
    best = None
    for fraction in settings['active_fractions']:
        active = max(1, math.floor(design['enabled_sms'] * fraction))
        for bw_fraction in settings['bandwidth_fractions']:
            hbw, lbw = design['hbm_bytes_s'] * bw_fraction, design['l2_bytes_s'] * bw_fraction
            normalized = work + settings['special_work_equivalent'] * special
            compute = normalized / (active * design['vector_work_s_per_sm'])
            l2_time = (read_bytes + write_bytes) / lbw
            hbm_bytes = read_bytes + write_bytes if cold or working_bytes > design['l2_bytes'] else 0
            hbm_time = hbm_bytes / hbw
            # One kernel: explicit memory/compute roofline, launch serial. Coarse lower-fidelity backend.
            service = max(compute, l2_time, hbm_time, 1e-15)
            envelope = base_power(design, power) + (active * design['vector_work_s_per_sm'] * power['vector_j_per_work'] if normalized else 0)
            envelope += (lbw * power['l2_j_per_byte'] if read_bytes + write_bytes else 0)
            envelope += (hbw * power['hbm_j_per_byte'] if hbm_bytes else 0)
            if cap is not None and envelope > cap:
                continue
            seconds = service + (settings['launch_s'] if launch else 0)
            energy = (base_power(design, power) * seconds + normalized * power['vector_j_per_work']
                      + (read_bytes + write_bytes) * power['l2_j_per_byte'] + hbm_bytes * power['hbm_j_per_byte'])
            row = {'name': name, 'seconds': seconds, 'energy_j_proxy': energy, 'power_envelope_w_proxy': envelope,
                   'matrix_service_s': 0, 'vector_service_s': compute, 'l2_service_s': l2_time,
                   'hbm_service_s': hbm_time, 'link_service_s': 0, 'active_sms': active,
                   'hbm_bytes': hbm_bytes, 'l2_bytes': read_bytes + write_bytes,
                   'bottleneck': max({'vector': compute, 'l2': l2_time, 'hbm': hbm_time}, key=lambda x: {'vector': compute, 'l2': l2_time, 'hbm': hbm_time}[x])}
            if best is None or seconds < best['seconds']:
                best = row
    return best


def matrix_stage(name, groups, n, k, activation_fmt, weight_fmt, design, profile, working_bytes, settings, power, cap):
    # groups = {M: number of distinct weight matrices}; no cross-expert weight reuse.
    mode = profile['modes'][activation_fmt]
    native = mode['native_k']
    best = None
    useful = sum(m * count for m, count in groups.items()) * n * k
    for tm, tn in settings['tiles']:
        tk = max(native, settings['tile_k'])
        scratch = 2 * (packed(tm, tk, activation_fmt) + packed(tn, tk, activation_fmt)) + 4 * tm * tn
        if weight_fmt != activation_fmt:
            scratch += 2 * packed(tn, tk, weight_fmt)
        if scratch > design['sram_bytes'] or scratch > design['l2_bytes']:
            continue
        reads_a = sum(count * packed(m, k, activation_fmt) * math.ceil(n / tn) for m, count in groups.items())
        reads_b = sum(count * packed(n, k, weight_fmt) * math.ceil(m / tm) for m, count in groups.items())
        writes = sum(count * 2 * m * n for m, count in groups.items())
        weights = sum(groups.values()) * packed(n, k, weight_fmt)
        inputs = sum(count * packed(m, k, activation_fmt) for m, count in groups.items())
        # B fetched once per operator; outer-cache reuse requires a stored-weight N-panel.
        panel_bytes = packed(min(n, tn), k, weight_fmt) + packed(tm, k, activation_fmt) + 4 * tm * min(n, tn)
        if panel_bytes > design['l2_bytes']:
            continue
        # N-panel outer loop retains B; spilled A must be fetched for each N panel.
        spill = inputs * math.ceil(n / tn) + writes if working_bytes > design['l2_bytes'] else 0
        hbm_bytes = weights + spill
        expanded = sum(count * n * k * math.ceil(m / tm) for m, count in groups.items()) if weight_fmt != activation_fmt else 0
        issued = sum(count * math.ceil(m / 4) * math.ceil(n / 4) * 16 * math.ceil(k / native) for m, count in groups.items())
        tiles = sum(count * math.ceil(m / tm) * math.ceil(n / tn) for m, count in groups.items())
        for fraction in settings['active_fractions']:
            active = min(max(1, math.floor(design['enabled_sms'] * fraction)), max(1, tiles),
                         max(1, design['l2_bytes'] // scratch))
            vector_time = expanded * settings['unpack_work_per_value'] / (active * design['vector_work_s_per_sm'])
            matrix_time = issued / (active * 64 * design['clock_hz']) + math.ceil(tiles / active) * mode['latency_cycles'] / design['clock_hz']
            for bw_fraction in settings['bandwidth_fractions']:
                hbw, lbw = design['hbm_bytes_s'] * bw_fraction, design['l2_bytes_s'] * bw_fraction
                hbm_time = hbm_bytes / hbw
                l2_time = (reads_a + reads_b + writes) / lbw
                batches = max(1, math.ceil(tiles / active) * math.ceil(k / tk))
                # Homogeneous three-stage pipeline: preserve first fill/final drain.
                core_time = matrix_time + vector_time
                times = [hbm_time / batches, l2_time / batches, core_time / batches]
                pipeline = sum(times) + (batches - 1) * max(times)
                seconds = pipeline + settings['launch_s']
                power_mode = power.get('dp_mode_proxies', {}).get(activation_fmt, activation_fmt)
                dp_w = profile['modes'][power_mode]['power_dynamic_w']
                require(dp_w is not None, 'DP mode needs an explicit power proxy')
                envelope = base_power(design, power) + active * 64 * dp_w * power['dp_activity_multiplier']
                if expanded:
                    envelope += active * design['vector_work_s_per_sm'] * power['vector_j_per_work']
                envelope += hbw * power['hbm_j_per_byte'] + lbw * power['l2_j_per_byte']
                if cap is not None and envelope > cap:
                    continue
                energy = (base_power(design, power) * seconds + issued * dp_w / design['clock_hz'] * power['dp_activity_multiplier']
                          + expanded * settings['unpack_work_per_value'] * power['vector_j_per_work']
                          + hbm_bytes * power['hbm_j_per_byte'] + (reads_a + reads_b + writes) * power['l2_j_per_byte'])
                components = {'matrix': matrix_time, 'vector_unpack': vector_time, 'hbm': hbm_time, 'l2': l2_time}
                row = {'name': name, 'seconds': seconds, 'energy_j_proxy': energy, 'power_envelope_w_proxy': envelope,
                       'matrix_service_s': matrix_time, 'vector_service_s': vector_time, 'hbm_service_s': hbm_time,
                       'l2_service_s': l2_time, 'link_service_s': 0, 'active_sms': active, 'hbm_bytes': hbm_bytes,
                       'l2_bytes': reads_a + reads_b + writes, 'useful_macs': useful, 'dp_issues': issued,
                       'tile_m': tm, 'tile_n': tn, 'tile_k': tk, 'scratch_bytes': scratch,
                       'bottleneck': max(components, key=components.get)}
                if best is None or seconds < best['seconds']:
                    best = row
    return best


def communication(name, amount, design, devices, settings, power, cap):
    if devices == 1:
        return {'name': name, 'seconds': 0, 'energy_j_proxy': 0, 'power_envelope_w_proxy': 0,
                'matrix_service_s': 0, 'vector_service_s': 0, 'hbm_service_s': 0, 'l2_service_s': 0,
                'link_service_s': 0, 'active_sms': 0, 'hbm_bytes': 0, 'l2_bytes': 0, 'bottleneck': 'link'}
    for fraction in settings['bandwidth_fractions']:
        rate = design['link_bytes_s'] * fraction
        l2_rate = design['l2_bytes_s'] * fraction
        l2_time = 2 * amount / l2_rate  # send read + receive write
        seconds = max(amount / rate, l2_time) + (devices - 1) * design['link_latency_s']
        envelope = base_power(design, power) + rate * power['link_j_per_byte'] + l2_rate * power['l2_j_per_byte']
        if cap is None or envelope <= cap:
            return {'name': name, 'seconds': seconds, 'energy_j_proxy': base_power(design, power) * seconds + amount * power['link_j_per_byte'] + 2 * amount * power['l2_j_per_byte'],
                    'power_envelope_w_proxy': envelope, 'matrix_service_s': 0, 'vector_service_s': 0,
                    'hbm_service_s': 0, 'l2_service_s': l2_time, 'link_service_s': amount / rate, 'active_sms': 0,
                    'hbm_bytes': 0, 'l2_bytes': 2 * amount, 'bottleneck': 'link' if amount / rate >= l2_time else 'l2'}
    return None


def evaluate(model, tokens, plan, fusion, design, profile, settings, power, cap, route='balanced'):
    require(model['n_shared_experts'] == 1, 'current subgraph requires one shared expert')
    devices = settings['devices']
    fmt = {'w4a8': Q, 'routed_mxfp4': E, 'routed_nvfp4': 'nvfp4'}[plan]
    wfmt = 'nvfp4' if plan == 'routed_nvfp4' else E
    ranks = routing(model, tokens, devices, route)
    local = tokens // devices
    d, f = model['dim'], model['moe_inter_dim']
    max_assignments = max(sum(m*c for m,c in rank.items()) for rank in ranks)
    working = max_assignments * (2*d + 6*f) + local*d*4
    resident = resident_bytes(model, plan, devices, settings['reserved_hbm_bytes'])
    if resident + working > design['hbm_capacity_bytes']:
        return {'status': 'capacity_infeasible', 'resident_bytes': resident, 'working_bytes': working}, []
    rows = []
    def vec(name, work, special, read, write, live=working, cold=False, launch=True):
        rows.append(vector_stage(name, work, special, read, write, live, design, settings, power, cap, cold, launch))
    def quant(name, count, width, qfmt):
        recipe = settings['quant_recipe']
        q = quantization_work(count, width, qfmt, recipe, fused_producer=fusion,
                              producer_allows_fusion=fusion, keep_high_precision_output=True)
        vec(name, q['work']['vector_work'], q['work']['special_work'], q['source_read_bytes'],
            q['output_payload_bytes'] + q['output_scale_bytes'], launch=not fusion)
    vec('norm', 5*local*d, local, 2*local*d, 2*local*d, cold=True)
    vec('router', 2*local*d*model['n_routed_experts'], local*model['n_routed_experts'],
        2*local*d + 4*d*model['n_routed_experts'], 4*local*model['n_activated_experts'])
    for qfmt in sorted({fmt, Q}):  # shared experts retain A8; shared input quantized once per format
        quant('input_quant_'+qfmt, local, d, qfmt)
    remote = (devices-1)/devices
    amount = packed(max_assignments, d, fmt) * remote
    rows.append(communication('dispatch', amount, design, devices, settings, power, cap))
    for name,n,k in [('expert_gate',f,d),('expert_up',f,d),('expert_down',d,f)]:
        if name == 'expert_down':
            vec('expert_swiglu', 4*max_assignments*f, max_assignments*f, 4*max_assignments*f, 2*max_assignments*f)
            quant('expert_down_quant', max_assignments, f, fmt)
        costs = [matrix_stage(name, g, n, k, fmt, wfmt, design, profile, working, settings, power, cap) for g in ranks if g]
        if costs and all(costs):
            slow = dict(max(costs, key=lambda x:x['seconds']))
            slow['energy_j_proxy'] = max(c['energy_j_proxy'] + base_power(design, power) * (slow['seconds'] - c['seconds']) for c in costs)
            slow['power_envelope_w_proxy'] = max(c['power_envelope_w_proxy'] for c in costs)
            rows.append(slow)
        else:
            rows.append(None)
    for name,n,k in [('shared_gate',f,d),('shared_up',f,d),('shared_down',d,f)]:
        if name == 'shared_down':
            vec('shared_swiglu',4*local*f,local*f,4*local*f,2*local*f)
            quant('shared_down_quant',local,f,Q)
        rows.append(matrix_stage(name,{local:model['n_shared_experts']},n,k,Q,Q,design,profile,working,settings,power,cap))
    rows.append(communication('combine', 2*max_assignments*d*remote,design,devices,settings,power,cap))
    vec('residual',local*d*(model['n_activated_experts']+2),0,2*local*d*(model['n_activated_experts']+1),2*local*d)
    if any(r is None for r in rows):
        return {'status':'power_or_mapping_infeasible','resident_bytes':resident,'working_bytes':working},[]
    seconds=sum(r['seconds'] for r in rows)
    return {'status':'analytical_subgraph','seconds':seconds,'energy_j_proxy_upper_per_rank':sum(r['energy_j_proxy'] for r in rows),
            'power_envelope_w_proxy':max(r['power_envelope_w_proxy'] for r in rows),
            'resident_bytes':resident,'working_bytes':working,
            'useful_macs_routed_global':tokens*model['n_activated_experts']*3*d*f,
            'quant_seconds':sum(r['seconds'] for r in rows if 'quant' in r['name']),
            'unpack_service_s':sum(r['vector_service_s'] for r in rows if r['name'].startswith('expert_') and 'quant' not in r['name'] and 'swiglu' not in r['name']),
            'largest_stage':max(rows,key=lambda r:r['seconds'])['name'],
            'bottleneck':max(rows,key=lambda r:r['seconds'])['bottleneck']},rows
