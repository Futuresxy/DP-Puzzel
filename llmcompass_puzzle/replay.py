"""Replay pinned LLMCompass A100 matrix timing on CPU, without GPU measurements."""

import argparse
from contextlib import chdir
import importlib
import importlib.metadata
import math
from pathlib import Path

from ratio_dse.common import ROOT, digest, read_json, require
from .backend import LOCK, load_cpu_matmul, load_cpu_operator
from .characterize import write_json, write_rows


def run(output):
    module = load_cpu_matmul()
    import pandas as pd
    device = importlib.import_module("hardware_model.device").device_dict["A100_80GB_fp16"]
    types = importlib.import_module("software_model.utils")
    columns = ["M", "N", "K", "ArrayHeight", "ArrayWidth", "Dataflow", "cycle_count", "util_rate"]
    table = pd.DataFrame(columns=columns, dtype=float).set_index(columns[:6])
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "systolic_array_model/temp").mkdir(parents=True)
    rows = []
    with chdir(output):
        for m, n, k in ((16, 16, 16), (64, 64, 128), (128, 256, 512)):
            # First row directly exercises SCALE-Sim at a small shape.
            cycles = module.Matmul.simulate_systolic_array_cycle_count(table, m, n, k, 16, 16, 1)
            require(cycles >= math.ceil(m * n * k / 256), "scalar array violates arithmetic lower bound")
            row = {"m": m, "n": n, "k": k, "scalar_array_cycles": cycles,
                   "upstream_a100_gemm_seconds": None, "mapping": None, "status": "upstream_cpu_replay"}
            if m >= 32:
                op = module.Matmul(types.data_type_dict["fp16"])
                op(types.Tensor([m, k]), types.Tensor([k, n]))
                op.look_up_table = table
                seconds = op.compile_and_simulate(device, "heuristic-GPU")
                require(math.isfinite(seconds) and seconds > 0, "invalid upstream latency")
                row.update(upstream_a100_gemm_seconds=seconds, mapping=vars(op.best_mapping))
            rows.append(row)
    write_rows(output / "a100_replay.csv", rows)
    softmax = load_cpu_operator("softmax")
    vector_rows = []
    for m, n in ((64, 128), (128, 512)):
        op = softmax.Softmax(types.data_type_dict["fp16"])
        op(types.Tensor([m, n]))
        seconds = op.compile_and_simulate(device)
        require(math.isfinite(seconds) and seconds > 0, "invalid upstream vector latency")
        vector_rows.append({"operator": "softmax", "m": m, "n": n,
                            "seconds": seconds, "mapping": vars(op.best_mapping),
                            "status": "upstream_cpu_replay"})
    write_rows(output / "a100_vector_replay.csv", vector_rows)
    write_json(output / "manifest.json", {
        "stage": "S1_upstream_reference_replay", "upstream_commit": read_json(LOCK)["commit"],
        "adapter": "eager torch import becomes optional in matmul and softmax; CPU timing logic unchanged",
        "source_lock_sha256": digest(LOCK), "adapter_sha256": digest(Path(__file__).with_name("backend.py")),
        "replay_source_sha256": digest(Path(__file__)),
        "support_sources_sha256": {str(p.relative_to(ROOT)): digest(p) for p in
                                   (Path(__file__).with_name("characterize.py"), ROOT / "ratio_dse/common.py")},
        "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scalesim")},
        "output_sha256": digest(output / "a100_replay.csv"), "gpu_measurements": False,
        "vector_output_sha256": digest(output / "a100_vector_replay.csv"),
        "physical_model": "original scalar systolic A100 model; not DP replacement or DeepSeek inference",
        "clock_hz": device.compute_module.clock_freq, "active_sms": device.compute_module.core_count,
        "hbm_bytes_s": device.io_module.bandwidth, "l2_bytes_cycle": device.compute_module.l2_bandwidth_per_cycle,
    })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows = run(args.output)
        print(f"Replayed {len(rows)} upstream cases; no GPU measurement or new-DP performance claim.")
    except (ValueError, OSError, KeyError, ImportError) as exc:
        parser.exit(2, f"replay: {exc}\n")


if __name__ == "__main__":
    main()
