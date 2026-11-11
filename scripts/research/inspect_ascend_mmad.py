#!/usr/bin/env python3
"""Compile the official Ascend C Mmad path and inspect its IR and machine words.

Requires an existing official devkit checkout and BiSheng compiler. This script
does not download/install tools or execute the generated device kernels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def text_section(path):
    """Read .text from the compiler's ELF64 little-endian object."""
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected ELF64 little-endian object")
    offset = struct.unpack_from("<Q", data, 40)[0]
    size, count, names_index = struct.unpack_from("<HHH", data, 58)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size)
                for i in range(count)]
    names = sections[names_index]
    strings = data[names[4]:names[4] + names[5]]
    for section in sections:
        name = strings[section[0]:].split(b"\0", 1)[0]
        if name == b".text":
            return data[section[4]:section[4] + section[5]]
    raise ValueError("Object has no .text section")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--devkit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    devkit = args.devkit.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name("ascend_mmad_probe.cpp").resolve()
    base = [str(compiler), "-std=c++17", "-O2", "-x", "cce",
            "--cce-aicore-only", "--cce-aicore-arch=dav-c220-cube",
            "-D__NPU_ARCH__=2201", "-I" + str(devkit / "include"),
            "-I" + str(devkit / "include/basic_api"), "-I" + str(devkit)]
    shapes = [(128, 128, k) for k in [16, 32, 64, 96, 128, 192, 256, 257,
                                     512, 4095, 4096]]
    shapes += [(16, 16, 2048), (16, 16, 2049), (128, 256, 64),
               (176, 176, 176), (192, 192, 192)]
    summary = {
        "scope": "compile_only", "target": "dav-c220-cube",
        "compiler_version": subprocess.check_output(
            [str(compiler), "--version"], text=True).splitlines()[0],
        "probe_sha256": sha256(source),
        "inspector_sha256": sha256(Path(__file__)),
        "kernel_execution": "not_run", "numerical_validation": "not_run",
        "capacity_source": "official A2/A3 FP16-to-FP32 L0 contract",
        "opcode_source": "Ascend/msopprof@a52c8694979016be703006ec242901519bef31d8",
        "opcode_mask": "0xefc00001", "opcode_key": "0xe0c00000", "cases": []}
    for m, n, k in shapes:
        name = f"M{m}N{n}K{k}"
        paths = {ext: output / f"{name}.{ext}" for ext in ["o", "bc", "ll", "s", "cc1.o"]}
        aligned = [((v + 15) // 16) * 16 for v in [m, n, k]]
        ma, na, ka = aligned
        sizes = {"l0a_bytes": ma * ka * 2, "l0b_bytes": ka * na * 2,
                 "l0c_bytes": ma * na * 4}
        case = {"m": m, "n": n, "k": k, **sizes,
                "within_dimension_contract": all(0 < v <= 4095 for v in [m, n, k]),
                "fits_l0_capacity": sizes["l0a_bytes"] <= 65536
                    and sizes["l0b_bytes"] <= 65536 and sizes["l0c_bytes"] <= 131072}
        command = base + [f"-DPROBE_M={m}", f"-DPROBE_N={n}", f"-DPROBE_K={k}",
                          "-c", str(source), "-o", str(paths["o"])]
        result = subprocess.run(command + ["-v"], text=True, capture_output=True)
        (output / f"{name}.log").write_text(result.stdout + result.stderr)
        case["compile_exit_code"] = result.returncode
        if result.returncode:
            case["diagnostic"] = result.stderr[-3000:]
            paths["o"].unlink(missing_ok=True)
        else:
            text = text_section(paths["o"])
            if len(text) % 4:
                raise ValueError("Expected 32-bit A2 instruction alignment")
            case["mmad_machine_words"] = [
                {"offset": offset, "word": f"0x{word:08x}"}
                for offset in range(0, len(text), 4)
                if ((word := struct.unpack_from("<I", text, offset)[0]) & 0xefc00001) == 0xe0c00000]
            case["machine_mmad_count"] = len(case["mmad_machine_words"])
            bc_command = command[:-1] + [str(paths["bc"]), "-emit-llvm"]
            subprocess.run(bc_command, check=True, capture_output=True)
            # Preserve the driver's target and LLVM options for backend output.
            # Require identical .text bytes before using its readable assembly.
            invocation = next(line.strip() for line in result.stderr.splitlines()
                              if line.strip().startswith(f'"{compiler}" -cc1 '))
            original = shlex.split(invocation)
            options = []
            for i, value in enumerate(original[:-1]):
                if value == "-mllvm":
                    options += [value, original[i + 1]]
            cc1 = [str(compiler), "-cc1", "-triple", "hiipu64-hisilicon-cce",
                   "-target-cpu", "dav-c220-cube", "-O2", "-mframe-pointer=all",
                   *options, "-x", "ir", str(paths["bc"]), "-emit-obj",
                   "-o", str(paths["cc1.o"])]
            output_index = cc1.index("-o") + 1
            subprocess.run(cc1, check=True, capture_output=True)
            case["cc1_text_matches_driver_object"] = text == text_section(paths["cc1.o"])
            ir_command = cc1.copy()
            ir_command[ir_command.index("-emit-obj")] = "-emit-llvm"
            ir_command[output_index] = str(paths["ll"])
            subprocess.run(ir_command, check=True, capture_output=True)
            ir = paths["ll"].read_text()
            match = re.search(r"call void @llvm\.hivm\.MAD\.f162f32[^\n]*i64 (-?\d+)", ir)
            if match is None:
                raise ValueError(f"Missing MAD configuration in IR for {name}")
            config = int(match.group(1)) & ((1 << 64) - 1)
            case["config_u64"] = f"0x{config:016x}"
            case["encoded_shape"] = {"m": config & 4095,
                                     "k": (config >> 12) & 4095,
                                     "n": (config >> 24) & 4095}
            case["shape_matches_encoding"] = case["encoded_shape"] == {"m": m, "k": k, "n": n}
            cc1[cc1.index("-emit-obj")] = "-S"
            cc1[output_index] = str(paths["s"])
            subprocess.run(cc1, check=True, capture_output=True)
            assembly = paths["s"].read_text()
            case["assembly_mmad_lines"] = re.findall(r"^\s*MMAD\.f162f32[^\n]*", assembly, re.M)
            case["sha256"] = {ext: sha256(path) for ext, path in paths.items()}
            if case["machine_mmad_count"] != len(case["assembly_mmad_lines"]):
                raise ValueError(f"Assembly/machine count mismatch for {name}")
            if not case["cc1_text_matches_driver_object"]:
                raise ValueError(f"Frontend/driver object mismatch for {name}")
            if case["within_dimension_contract"] and not case["shape_matches_encoding"]:
                raise ValueError(f"Shape/config mismatch for {name}")
        summary["cases"].append(case)
        print(f"{name}: compiler={case['compile_exit_code']}, "
              f"machine_MMAD={case.get('machine_mmad_count')}, "
              f"fits_L0={case['fits_l0_capacity']}", flush=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    failed = [c for c in summary["cases"]
              if c["within_dimension_contract"] and c["fits_l0_capacity"]
              and (c["compile_exit_code"] != 0 or c.get("machine_mmad_count") != 1)]
    if failed:
        raise SystemExit(f"{len(failed)} capacity-valid probes failed; see summary.json and logs")


if __name__ == "__main__":
    main()
