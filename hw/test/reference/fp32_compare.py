"""Independent FP32 result/ULP comparison; no RTL model or fingerprints."""
from pathlib import Path
import re
import struct

def read_hex(path: Path, width: int, count: int | None = None) -> list[int]:
    """One unsigned HEX token per line; reject truncation, X/Z, comments and blanks."""
    result = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not re.fullmatch(r'[0-9a-fA-F]{1,' + str((width+3)//4) + r'}', line):
            raise ValueError(f'{path}:{line_no}: expected one {width}-bit HEX token')
        value = int(line, 16)
        if value >= 1 << width:
            raise ValueError(f'{path}:{line_no}: value exceeds {width} bits')
        result.append(value)
    if not result or (count is not None and len(result) != count):
        raise ValueError(f'{path}: expected {count} tokens, found {len(result)}')
    return result



def ordered(bits: int) -> int:
    return (~bits & 0xffffffff) if bits & 0x80000000 else bits | 0x80000000


def fp32_value(bits: int) -> float:
    return struct.unpack('>f', bits.to_bytes(4, 'big'))[0]


def compare_word(actual: int, golden: int) -> tuple[int | None, str]:
    # Zero and all nonfinite encodings have a strict bit contract, independent of ULP.
    special = lambda b: (b & 0x7fffffff) == 0 or (b & 0x7f800000) == 0x7f800000
    if special(actual) or special(golden):
        return None, 'EXACT' if actual == golden else 'SPECIAL_BITS_MISMATCH'
    ulp = abs(ordered(actual) - ordered(golden))
    return ulp, 'EXACT' if ulp == 0 else ('ULP_LT_4' if ulp < 4 else 'ULP_GE_4')


def compare_files(actual_path: Path, golden_path: Path, output: Path, count: int) -> dict:
    actual, golden = read_hex(actual_path, 32, count), read_hex(golden_path, 32, count)
    buckets = {'finite_ulp_0': 0, 'finite_ulp_1': 0, 'finite_ulp_2_3': 0,
               'finite_ulp_ge_4': 0, 'special_exact': 0, 'special_mismatch': 0}
    rows = ['txn\tactual_hex\tgolden_hex\tulp\texact\tstatus\tactual_value\tgolden_value']
    ulps, exact, bad = [], 0, []
    for i, (a, g) in enumerate(zip(actual, golden)):
        ulp, status = compare_word(a, g)
        exact += a == g
        if ulp is None:
            buckets['special_exact' if status == 'EXACT' else 'special_mismatch'] += 1
        else:
            ulps.append(ulp)
            key = 'finite_ulp_0' if ulp == 0 else ('finite_ulp_1' if ulp == 1 else
                  ('finite_ulp_2_3' if ulp < 4 else 'finite_ulp_ge_4'))
            buckets[key] += 1
        if status in ('ULP_GE_4', 'SPECIAL_BITS_MISMATCH'):
            bad.append(i)
        rows.append(f'{i}\t{a:08x}\t{g:08x}\t{ulp if ulp is not None else "NA"}\t'
                    f'{int(a == g)}\t{status}\t{fp32_value(a):.9g}\t{fp32_value(g):.9g}')
    output.write_text('\n'.join(rows) + '\n')
    reasons = []
    if buckets['finite_ulp_ge_4']: reasons.append('ULP_GE_4')
    if buckets['special_mismatch']: reasons.append('SPECIAL_BITS_MISMATCH')
    if exact * 10 < count * 9: reasons.append('EXACT_RATE_BELOW_90')
    return {'transactions': count, 'exact': exact, 'exact_fraction': exact/count,
            'max_finite_ulp': max(ulps, default=None), 'buckets': buckets,
            'failed_transactions': bad, 'reasons': reasons, 'passed': not reasons}


def compare_segments(actual_path: Path, golden_path: Path, segments: list[dict], output: Path) -> dict:
    """Retain each original dataset's gate and keep ones out of the precision rate."""
    if not segments:
        raise ValueError('merged data needs explicit segments')
    count = segments[-1]['stop']
    actual, golden = read_hex(actual_path, 32, count), read_hex(golden_path, 32, count)
    results, reasons = [], []
    precision_count = precision_exact = cursor = 0
    rows = ['dataset\tstart\tstop_exclusive\tcount\texact\tmax_ulp\tprecision_rate_member\tpassed\treasons']
    for segment in segments:
        start, stop = segment['start'], segment['stop']
        if start != cursor or stop <= start or segment['count'] != stop-start:
            raise ValueError('noncontiguous or invalid segment boundaries')
        observed, expected = actual[start:stop], golden[start:stop]
        exact = sum(a == g for a,g in zip(observed,expected))
        comparisons = [compare_word(a,g) for a,g in zip(observed,expected)]
        failures = []
        if any(status == 'ULP_GE_4' for _,status in comparisons): failures.append('ULP_GE_4')
        if any(status == 'SPECIAL_BITS_MISMATCH' for _,status in comparisons):
            failures.append('SPECIAL_BITS_MISMATCH')
        if segment['include_in_precision_rate']:
            precision_count += stop-start
            precision_exact += exact
            if exact*10 < (stop-start)*9: failures.append('EXACT_RATE_BELOW_90')
        if segment['require_bit_exact'] and exact != stop-start:
            failures.append('SMOKE_BITS_MISMATCH')
        max_ulp = max((ulp for ulp,_ in comparisons if ulp is not None),default=None)
        item = {k:segment[k] for k in ('dataset','start','stop','count','include_in_precision_rate')}
        item.update(exact=exact,max_finite_ulp=max_ulp,passed=not failures,reasons=failures)
        results.append(item)
        reasons.extend(f'{segment["dataset"]}:{failure}' for failure in failures)
        rows.append('\t'.join(str(x) for x in [segment['dataset'],start,stop,stop-start,exact,
                    max_ulp,segment['include_in_precision_rate'],not failures,','.join(failures) or 'NONE']))
        cursor = stop
    if precision_count <= 0:
        raise ValueError('no precision transactions in merged case')
    if precision_exact*10 < precision_count*9:
        reasons.append('MERGED_PRECISION_EXACT_RATE_BELOW_90')
    output.write_text('\n'.join(rows)+'\n')
    return {'segments':results,'precision_transactions':precision_count,'precision_exact':precision_exact,
            'precision_exact_fraction':precision_exact/precision_count,'passed':not reasons,'reasons':reasons}


def compare_random_case(actual_path: Path, golden_path: Path, segments: list[dict], output: Path) -> dict:
    """Random-1600 contract: <=2 finite FP32 steps, directed cases bit exact.

    The two zero signs occupy the same numerical position in ordinary cases.
    Nonfinite encodings are always strict; directed cases also check zero signs.
    Exact rates are statistics, not acceptance thresholds. This policy does not
    change the historical correct_961 comparator.
    """
    if not segments:
        raise ValueError('random cases require segments')
    count = segments[-1]['stop']
    actual, golden = read_hex(actual_path, 32, count), read_hex(golden_path, 32, count)
    numerical_order = lambda x: 0x80000000 - (x & 0x7fffffff) if x >> 31 else 0x80000000 + x
    rows = ['txn\tactual_hex\tgolden_hex\tfp32_steps\texact\tstatus']
    segment_rows = ['dataset\tstart\tstop_exclusive\tcount\texact\tmax_fp32_steps\tpassed\treasons']
    results, bad, all_steps, reasons = [], [], [], []
    buckets = {'finite_steps_0':0,'finite_steps_1':0,'finite_steps_2':0,
               'finite_steps_gt_2':0,'nonfinite_exact':0,'nonfinite_mismatch':0}
    precision_count = precision_exact = cursor = total_exact = 0
    for segment in segments:
        start, stop = segment['start'], segment['stop']
        if start != cursor or stop <= start or segment['count'] != stop-start:
            raise ValueError('invalid random segment boundaries')
        exact, steps, failures = 0, [], set()
        for i in range(start, stop):
            a, g = actual[i], golden[i]
            same = a == g
            exact += same
            nonfinite = (a & 0x7f800000) == 0x7f800000 or (g & 0x7f800000) == 0x7f800000
            distance = None if nonfinite else abs(numerical_order(a)-numerical_order(g))
            status = 'EXACT' if same else 'FP32_STEPS_LE_2'
            if nonfinite:
                buckets['nonfinite_exact' if same else 'nonfinite_mismatch'] += 1
                if not same:
                    status = 'SPECIAL_BITS_MISMATCH'
            else:
                steps.append(distance)
                buckets[f'finite_steps_{distance}' if distance <= 2 else 'finite_steps_gt_2'] += 1
                if distance > 2:
                    status = 'FP32_STEPS_GT_2'
            if segment['require_bit_exact'] and not same:
                status = 'DIRECTED_BITS_MISMATCH'
            if status in ('SPECIAL_BITS_MISMATCH','FP32_STEPS_GT_2','DIRECTED_BITS_MISMATCH'):
                failures.add(status)
                bad.append(i)
            rows.append(f'{i}\t{a:08x}\t{g:08x}\t{distance if distance is not None else "NA"}\t{int(same)}\t{status}')
        if segment['include_in_precision_rate']:
            precision_count += stop-start
            precision_exact += exact
        total_exact += exact
        all_steps.extend(steps)
        item = dict(dataset=segment['dataset'],start=start,stop=stop,count=stop-start,
                    exact=exact,exact_fraction=exact/(stop-start),max_fp32_steps=max(steps,default=None),
                    passed=not failures,reasons=sorted(failures))
        results.append(item)
        reasons.extend(f'{segment["dataset"]}:{failure}' for failure in sorted(failures))
        segment_rows.append('\t'.join(map(str,(segment['dataset'],start,stop,stop-start,exact,
                                             item['max_fp32_steps'],item['passed'],','.join(sorted(failures)) or 'NONE'))))
        cursor = stop
    (output/'comparison.txt').write_text('\n'.join(rows)+'\n')
    (output/'segments.txt').write_text('\n'.join(segment_rows)+'\n')
    return dict(transactions=count,exact=total_exact,exact_fraction=total_exact/count,
                max_finite_ulp=max(all_steps,default=None),max_fp32_steps=max(all_steps,default=None),
                metric='FP32 representable-step distance to exactly rounded golden; not real-valued ULP error',
                acceptance_policy='fp32_steps_le2_special_exact_v1',buckets=buckets,
                failed_transactions=bad,segments=results,precision_transactions=precision_count,
                precision_exact=precision_exact,precision_exact_fraction=precision_exact/precision_count,
                passed=not reasons,reasons=reasons)
