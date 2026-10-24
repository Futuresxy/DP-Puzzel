#!/usr/bin/env python3
"""Independent bit-level BF16 oracle and deterministic cycle-vector producer."""
import argparse
import json
from pathlib import Path
import random


def write_vectors(output, seed, random_cycles):
    rng = random.Random(seed)
    counters = {"cycles": 0, "valid": 0, "bubbles": 0, "resets": 0}
    held = None
    with Path(output).open("w", encoding="ascii") as stream:
        def emit(reset, valid, negate, bits):
            nonlocal held
            expected_valid = int(not reset and valid)
            if expected_valid:
                held = bits ^ (0x8000 if negate else 0)
            stream.write("{} {} {} {:04x} {} {} {:04x}\n".format(
                reset, valid, negate, bits, expected_valid, int(held is not None), held or 0))
            counters["cycles"] += 1
            counters["resets" if reset else "valid" if valid else "bubbles"] += 1

        emit(1, 0, 0, 0)
        emit(1, 1, 1, 0x7f80)
        directed = [0x0000, 0x8000, 0x3f80, 0xbf80, 0x0001, 0x8001,
                    0x007f, 0x0080, 0x7f7f, 0xff7f, 0x7f80, 0xff80,
                    0x7fc1, 0xffc1, 0x7f81, 0xff81]
        for bits in directed:
            for negate in (0, 1):
                emit(0, 1, negate, bits)
                emit(0, 0, 1 - negate, bits ^ 0xffff)
        emit(1, 1, 1, 0xffff)
        for bits in range(65536):
            emit(0, 1, 0, bits)
            emit(0, 1, 1, bits)
            if bits % 257 == 0:
                emit(0, 0, rng.randrange(2), rng.randrange(65536))
        for cycle in range(random_cycles):
            emit(int(cycle % 251 == 0), int(rng.random() < 0.75),
                 rng.randrange(2), rng.randrange(65536))
        for _ in range(4):
            emit(0, 0, 1, 0xffff)
    return {"schema_version": 1, "seed": seed, "counts": counters,
            "exhaustive_bit_patterns": 65536, "exhaustive_negate_modes": 2,
            "directed_patterns": ["{:04x}".format(v) for v in directed],
            "random_cycles": random_cycles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--random-cycles", required=True, type=int)
    args = parser.parse_args()
    if args.random_cycles < 1:
        parser.error("random-cycles must be positive")
    metadata = write_vectors(args.output, args.seed, args.random_cycles)
    Path(str(args.output) + ".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata["counts"]))


if __name__ == "__main__":
    main()
