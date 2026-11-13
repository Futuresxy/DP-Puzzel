"""Four exclusive operating modes, fixed peripheral area per core."""
import numpy as np
import workloads as base
FORMATS=("bf16","mxfp8_e4m3","mxfp4_e2m1","nvfp4")
def deploy(hw, alpha=.30, growth=0., baseline_cores=1, integer=False):
    """Fixed peripheral area per baseline core, optional incremental growth.

    A_core0=A_DP0/alpha. Budget=N0*A_core0 is a model budget, not die area.
    """
    area0 = hw[0]["area"]
    core0 = area0/alpha
    designs = []
    for h in hw:
        a = h["area"] + core0-area0 + growth*(h["area"]-area0)
        n = baseline_cores*core0/a
        if integer:
            n = np.floor(n + 1e-12)
        design = dict(ratio=h["ratio"], area=a, count=n, capacity=n*h["capacity"])
        if "power" in h:
            design["power"] = n*h["power"]
        designs.append(dict(design, total_power=None))
    return designs

def mapped_work(model, phase, context, profile, batch=1):
    rows = base.work(model, phase, context if phase == "prefill" else context-1, batch=batch)
    totals = np.zeros(4)
    excluded = 0
    ledger = []
    for original in rows:
        r = dict(original)
        fmt = {"BF16":"bf16", "FP8":"mxfp8_e4m3", "FP4":"mxfp4_e2m1"}.get(r["precision"])
        reason = "inherited useful-work reference/paper profile"
        if r["kernel"].startswith("moe.routed.") and profile != "reference_work":
            fmt = "mxfp4_e2m1" if profile == "mxfp4_experts" else "nvfp4"
            reason = "routed experts only; shared experts unchanged"
        if r["kernel"] == "o_group" and profile == "nvfp4_experts_fp8_woa":
            fmt = "mxfp8_e4m3"
            reason = "conditional NVIDIA grouped WO-A FP8 path"
        if fmt is None:
            excluded += r["flops"]
        else:
            totals[FORMATS.index(fmt)] += r["flops"]
        ledger.append(dict(**r, format=fmt or "FP32_excluded", mapping_basis=reason))
    return totals, excluded, ledger

def evaluate(designs, flops):
    f = np.asarray(flops, dtype=float)
    cap = np.array([d["capacity"] for d in designs])
    power = np.array([d["power"] for d in designs])
    time = (f/cap).sum(axis=1)/1e12
    energy = (f*power/cap).sum(axis=1)/1e12
    return time, energy
