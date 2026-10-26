"""Small file/provenance helpers shared only by the data preparation tools."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_mem(path, values, bits):
    """One unsigned hexadecimal storage word per LF line, earliest index first."""
    words = [int(value) for value in values]
    if any(value < 0 or value >= 1 << bits for value in words):
        raise ValueError(f"Value outside {bits}-bit memory word")
    digits = (bits + 3) // 4
    Path(path).write_text("".join(f"{value:0{digits}x}\n" for value in words), encoding="ascii")


def inventory(directory):
    directory = Path(directory)
    return [{"path": str(path.relative_to(directory)), "bytes": path.stat().st_size,
             "sha256": sha256(path)}
            for path in sorted(directory.rglob("*"))
            if path.is_file() and path.name != "manifest.json"]


def verify_inventory(directory, files):
    root = Path(directory).resolve()
    for entry in files:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or sha256(path) != entry["sha256"]:
            raise ValueError(f"Data fingerprint mismatch: {entry['path']}")
