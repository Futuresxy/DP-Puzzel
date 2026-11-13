"""Verified upstream loading and narrow adapters; no changes to upstream files."""

import copy
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from ratio_dse.common import ROOT, digest, require

LOCK = ROOT / "dependencies/llmcompass.json"


def upstream():
    lock = json.loads(LOCK.read_text())
    path = ROOT / lock["directory"]
    head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    require(head == lock["commit"], "LLMCompass checkout does not match its fixed revision")
    for name, expected in lock["upstream_source_sha256"].items():
        require(digest(path / name) == expected, f"modified upstream source: {name}")
    for sub in lock["submodules"]:
        subhead = subprocess.check_output(["git", "-C", str(path / sub["path"]), "rev-parse", "HEAD"],
                                          text=True).strip()
        require(subhead == sub["commit"], f"submodule revision mismatch: {sub['path']}")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    return path


def baseline_config(*, clock_hz=1_000_000_000):
    """A100 performance resources, distinct from physical area resources."""
    path = upstream()
    config = json.loads((path / "configs/GA100.json").read_text())
    config["name"] = "NVIDIA A100-derived normalized reference"
    config["device_count"] = 1
    config["device"]["frequency_Hz"] = clock_hz
    config["device"]["compute_chiplet"]["core_count"] = 108
    config["device"]["io"]["global_buffer_MB"] = 40
    io = config["device"]["io"]
    # template_to_system derives effective HBM bandwidth from channels and pin rate.
    io["bandwidth_per_pin_bit"] = 2_039e9 * 8 / (io["memory_channel_active_count"] * io["pin_count_per_channel"])
    # Upstream interprets this GB field as GiB; match the built-in 80e9-byte device.
    config["device"]["memory"]["total_capacity_GB"] = 80e9 / 1024**3
    # Physical 128 SM and 48 MiB remain the upstream cost scenario, not runtime resources.
    return config


def vector_bundle(config, scale):
    """Scale ALU counts and issue throughput together; keep warp width fixed."""
    require(scale in (0.5, 1, 2), "supported vector bundles: 0.5, 1, 2")
    result = copy.deepcopy(config)
    core = result["device"]["compute_chiplet"]["core"]
    vector = core["vector_unit"]
    vector["flop_per_cycle"] *= scale
    for key in ("int32_count", "fp16_count", "fp32_count", "fp64_count"):
        count = vector[key] * scale
        require(count == int(count), "vector bundle requires integer ALU counts")
        vector[key] = int(count)
    core["register_file"]["num_rdwr_ports"] = max(2, int(core["register_file"]["num_rdwr_ports"] * scale))
    return result


def chip_area(config):
    upstream()
    cost = importlib.import_module("cost_model.cost_model")
    compute, core, compute_parts = cost.calc_compute_chiplet_area_mm2(config, verbose=True)
    io, io_parts = cost.calc_io_die_area_mm2(config, verbose=True)
    return {"total_mm2": compute + io, "compute_mm2": compute, "io_mm2": io,
            "core": core, "compute_parts": compute_parts, "io_parts": io_parts}


def load_cpu_operator(operator):
    """Execute the pinned CPU simulator with only its eager torch import optional.

    Upstream PyTorch is used by GPU measurement helpers, not the CPU model.
    No fake torch module is injected. GPU measurement is outside this entry point.
    The one in-memory import edit is recorded in every replay manifest.
    """
    require(operator in ("matmul", "softmax"), "only audited matmul/softmax CPU paths are supported")
    path = upstream() / f"software_model/{operator}.py"
    name = f"software_model.{operator}"
    if name in sys.modules:
        return sys.modules[name]
    source = path.read_text()
    require("\nimport torch\n" in source, "expected pinned eager torch import")
    source = source.replace("\nimport torch\n", "\ntry:\n    import torch\nexcept ModuleNotFoundError:\n    torch = None\n", 1)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def load_cpu_matmul():
    return load_cpu_operator("matmul")
