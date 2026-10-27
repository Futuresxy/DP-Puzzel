"""Input-only, bounded-cancellation sampling for the normal research regression.

The contract uses exact products, not RTL outputs, error thresholds, shift
windows or a list of failing transaction IDs. Magnitude encodings/scales remain
random; product signs are conditioned to avoid severe cancellation at the
word, four-word group, sixteen-word block and complete-dot boundaries.
"""
from exact_dot import FORMATS, FP32, decode_binary, dequantize, multiply


NORMAL_DATASET = "random_1600_normal"
NORMAL_CONTRACT = {
    "version": "bounded_cancellation_v1",
    "maximum_cancellation_factor": 4,
    "rule": "4*abs(sum(terms)) >= sum(abs(terms))",
    "regions": "packed word; four words; sixteen words; full dot; all products plus C",
    "applies_to": ["ab_scale_random", "c_stratified_random"],
    "special_exception": "64 directed encoding tests, including homogeneous unit zero sums",
    "sign_sampling": "random feasible word/PG/lane sign flips from coherent product signs",
    "uses_rtl_outputs": False,
}


def product_regions(name, k):
    fmt = FORMATS[name]
    lanes = 1 if fmt.scale_kind == "none" else 2 if fmt.bits in (6, 8) else 4
    return sorted({(start, min(start+size, k))
                   for size in (lanes, 4*lanes, 16*lanes, k)
                   for start in range(0, k, size)}, key=lambda r: (r[1]-r[0], r[0]))


def products(name, a, b):
    return [multiply(x,y) for x,y in zip(dequantize(name,a),dequantize(name,b))]


def integer_terms(values):
    if any(x.special for x in values):
        raise ValueError("Normal-scope arithmetic requires finite inputs")
    exponent = min((x.exponent for x in values if x.coefficient),default=0)
    return [x.coefficient << (x.exponent-exponent) if x.coefficient else 0 for x in values]


def normal_scope_violations(name, a, b, c=0):
    terms = products(name,a,b)
    c_value = decode_binary(FP32,c)
    if any(x.special for x in terms) or c_value.special:
        return ["nonfinite ordinary input"]
    integers = integer_terms(terms+[c_value])
    violations = []
    for start,stop in product_regions(name,len(terms)):
        region = integers[start:stop]
        if 4*abs(sum(region)) < sum(abs(x) for x in region):
            violations.append(f"products[{start}:{stop}]")
    if 4*abs(sum(integers)) < sum(abs(x) for x in integers):
        violations.append("products+C")
    return violations


def condition_product_signs(name, a, b, rng):
    """Sample mixed product signs inside the declared input-conditioning scope.

    Begin with a randomly selected common product sign. Consider random flips
    of whole words/PGs and individual lanes, accepting only scope-preserving
    flips. This constructs valid samples directly rather than repeatedly
    discarding entire long low-bit vectors. A sign remains random; B's sign is
    correlated with A as explicitly recorded in NORMAL_CONTRACT.
    """
    weights = [abs(x) for x in integer_terms(products(name,a,b))]
    regions = product_regions(name,len(weights))
    totals = [sum(weights[start:stop]) for start,stop in regions]
    sums = totals.copy()
    memberships = [[j for j,(start,stop) in enumerate(regions) if start<=i<stop]
                   for i in range(len(weights))]
    signs = [1]*len(weights)
    fmt = FORMATS[name]
    lanes = 1 if fmt.scale_kind=="none" else 2 if fmt.bits in (6,8) else 4
    candidates = sorted({r for r in regions if r[1]-r[0] <= 4*lanes}
                        | {(i,i+1) for i in range(len(weights))})
    rng.shuffle(candidates)
    for start,stop in candidates:
        if not rng.getrandbits(1):
            continue
        changes = {}
        for i in range(start,stop):
            delta = -2*signs[i]*weights[i]
            for j in memberships[i]:
                changes[j] = changes.get(j,0)+delta
        if all(4*abs(sums[j]+delta)>=totals[j] for j,delta in changes.items()):
            for j,delta in changes.items():
                sums[j] += delta
            for i in range(start,stop):
                signs[i] = -signs[i]
    common_negative = rng.getrandbits(1)
    sign_bit = 1 << (FORMATS[name].bits-1)
    for i,sign in enumerate(signs):
        product_negative = common_negative ^ (sign<0)
        b.codes[i] = (b.codes[i] & (sign_bit-1)) | ((a.codes[i] & sign_bit) ^ (sign_bit if product_negative else 0))
    if normal_scope_violations(name,a,b):
        raise ValueError("Internal normal-scope sign construction failed")
    return a,b
