"""JSON contracts and reproducible run output shared by the two models."""

import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

from . import MODEL_VERSION, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
ANALYTICAL = "analytical_uncalibrated"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(name, value, minimum=1):
    require(type(value) is int and value >= minimum, f"{name} must be an integer >= {minimum}")
    return value


def number(name, value, minimum=0):
    require(type(value) in (int, float) and math.isfinite(value) and value >= minimum,
            f"{name} must be finite and >= {minimum}")
    return value


def ceil_div(n, d):
    return (n + d - 1) // d


def ratio(n, d):
    return n / d if d else None


def json_text(value, *, compact=False):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      indent=None if compact else 2, separators=(",", ":") if compact else None)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(prefix, value):
    return prefix + "-" + hashlib.sha256(json_text(value, compact=True).encode()).hexdigest()[:20]


def path_label(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def versioned(value, name):
    require(isinstance(value, dict) and type(value.get("schema_version")) is int
            and value["schema_version"] == SCHEMA_VERSION, f"{name} requires schema_version {SCHEMA_VERSION}")
    return value


def provenance(paths):
    return {path_label(path): digest(path) for path in sorted(set(map(Path, paths)))}


def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json_text(value, compact=True) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


def write_run(output, *, model, command, inputs, config, documents, tables, summary, extra_sources=()):
    """Publish a fresh output directory. The manifest is written last."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, value in documents.items():
            (output / name).write_text(json_text(value) + "\n", encoding="utf-8")
        for name, (rows, columns) in tables.items():
            write_csv(output / name, rows, columns)
        (output / "summary.md").write_text(summary, encoding="utf-8")
        sources = [*PACKAGE.glob("*.py"), *(PACKAGE / model).glob("*.py"), *extra_sources]
        manifest = {
            "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION, "model": model,
            "calibration_status": ANALYTICAL, "command": list(command), "config": config,
            "inputs_sha256": provenance(inputs), "sources_sha256": provenance(sources),
            "outputs_sha256": {path.name: digest(path) for path in sorted(output.iterdir())},
            "units": {"area": "um2", "time": "s", "frequency": "Hz", "power": "W",
                      "bandwidth": "byte/s", "bytes": "byte", "cycles": "cycle", "flop_per_mac": 2},
        }
        (output / "manifest.json").write_text(json_text(manifest) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(output)
        raise
