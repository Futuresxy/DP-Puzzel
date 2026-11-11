#!/usr/bin/env python3
"""Keep the newest two unreferenced, completed runs in each workflow."""
import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import fcntl
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FLOWS = {
    "cmodel": "test/runs/cmodel",
    "rtl": "test/runs/verilog",
    "dc": "hw/dc_syn/runs",
    "power": "hw/power/runs",
}
KEEP = 2
PIN = "retain.json"
STAMP = "%Y%m%dT%H%M%S%fZ"


def plain_path(root, path):
    """Check lexical containment and reject symlinks in the path."""
    relative = path.relative_to(root)
    return ".." not in relative.parts and not any(
        p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents
    )


def run_dirs(root, flow):
    base = root / FLOWS[flow]
    if base.is_dir() and plain_path(root, base):
        return sorted(p for p in base.iterdir() if p.is_dir() and not p.is_symlink())
    return []


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def finish_time(flow, path):
    if (path / ".running").exists() or (path / ".running").is_symlink():
        return None
    try:
        if flow in ("dc", "power"):
            name = r"dc_[A-Za-z_][A-Za-z0-9_$]*_\d{8}" if flow == "dc" else r"[A-Za-z0-9][A-Za-z0-9_.-]*"
            state_path = path / "state.json"
            if not re.fullmatch(name, path.name) or state_path.is_symlink():
                return None
            state = read_json(state_path)
            if state["phase"] not in ("finished", "failed"):
                return None
            return datetime.strptime(state["finished_utc"], STAMP).replace(tzinfo=timezone.utc)
        if not re.fullmatch(r"\d{8}T\d{12}Z", path.name):
            return None
        if flow == "cmodel":
            summary = path / "summary.json"
            if summary.is_symlink() or read_json(summary)["status"] not in ("passed", "failed"):
                return None
        else:
            reports = [p for p in path.glob("*-summary.json")
                       if re.fullmatch(r"(verilator|iverilog)-(verilog|systemverilog|both)-(all|existing|parameters)-summary\.json", p.name)
                       and not p.is_symlink()]
            if len(reports) != 1:
                return None
            records = read_json(reports[0])
            if not isinstance(records, list) or not records:
                return None
        return datetime.strptime(path.name, STAMP).replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def references(root, run_ids):
    if not run_ids:
        return set()
    patterns = [arg for name in sorted(run_ids) for arg in ("-e", name)]
    tracked = subprocess.run(["git", "grep", "-I", "-F", "-o", "-h", *patterns, "--"],
                             cwd=root, capture_output=True, text=True)
    if tracked.returncode not in (0, 1):
        raise ValueError("Could not check references in tracked files: " + tracked.stderr)
    found = set(tracked.stdout.splitlines())
    pattern = re.compile(r"(?<![\w.-])(?:" + "|".join(map(re.escape, sorted(run_ids))) + r")(?![\w.-])")
    for manifest in (root / "hw/rtl").glob("*/manifest.json"):
        if not plain_path(root, manifest):
            raise ValueError("Unsafe RTL manifest path: " + str(manifest.relative_to(root)))
        data = read_json(manifest)
        # validation_runs is historical bookkeeping. The current verified
        # scopes and gate receipt are the live references.
        found.update(pattern.findall(json.dumps([data.get(key) for key in ("verification", "verified_scopes")])))
    # A newly published local record can precede its Git commit.
    for base in ("hw/dc_syn/records", "hw/power/records", "test/results"):
        folder = root / base
        if not folder.is_dir():
            continue
        for record in folder.iterdir():
            if record.suffix in (".json", ".md") and record.is_file():
                if not plain_path(root, record):
                    raise ValueError("Unsafe record path: " + str(record.relative_to(root)))
                found.update(pattern.findall(record.read_text(encoding="utf-8")))
    for flow in ("dc", "power"):
        for run in run_dirs(root, flow):
            for name in ("inputs/resolved.json", "manifest.json", "inputs/manifest.json", "summary.json"):
                path = run / name
                if not plain_path(root, path):
                    raise ValueError("Unsafe analysis metadata path: " + str(path.relative_to(root)))
                if path.is_file():
                    found.update(set(pattern.findall(path.read_text(encoding="utf-8"))) - {run.name})
    return found


def is_ignored_untracked(root, path):
    relative = path.relative_to(root).as_posix() + "/"
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", relative], cwd=root)
    ignored = subprocess.run(["git", "check-ignore", "-q", "--", relative], cwd=root)
    return not tracked and ignored.returncode == 0


def plan(root):
    groups = {flow: run_dirs(root, flow) for flow in FLOWS}
    times = {p: finish_time(flow, p) for flow, paths in groups.items() for p in paths}
    used = references(root, {p.name for p, when in times.items() if when is not None})
    for flow, paths in groups.items():
        ordinary = []
        for path in paths:
            if (path / PIN).exists() or (path / PIN).is_symlink():
                yield path, "PINNED"
            elif times[path] is None:
                yield path, "UNCLASSIFIED_OR_ACTIVE"
            elif path.name in used or not is_ignored_untracked(root, path):
                yield path, "REFERENCED_OR_TRACKED"
            else:
                ordinary.append(path)
        ordinary.sort(key=lambda p: (times[p], p.name), reverse=True)
        for index, path in enumerate(ordinary):
            yield path, "KEEP" if index < KEEP else "DELETE"


def remove_run(root, path):
    flow = next(flow for flow, base in FLOWS.items() if path.parent == root / base)
    if not plain_path(root, path) or finish_time(flow, path) is None or (path / PIN).exists() or (path / PIN).is_symlink():
        raise ValueError("Run changed after planning: " + str(path.relative_to(root)))
    if not is_ignored_untracked(root, path):
        raise ValueError("Run is tracked or outside ignored outputs: " + str(path.relative_to(root)))
    if path.name in references(root, {path.name}):
        raise ValueError("Run is referenced: " + str(path.relative_to(root)))
    for directory, dirs, files in os.walk(path):
        if any((Path(directory) / name).is_symlink() for name in dirs + files):
            raise ValueError("Symlink inside run: " + str(path.relative_to(root)))
    shutil.rmtree(path)


@contextmanager
def mutation_lock(root):
    path = root / "test/runs/.retention.lock"
    if not plain_path(root, path):
        raise ValueError("Unsafe retention lock path")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def pin_run(root, path, reason):
    if (path.parent not in [root / base for base in FLOWS.values()] or not path.is_dir()
            or not plain_path(root, path) or not is_ignored_untracked(root, path)):
        raise ValueError("Pin requires an explicit ignored run directory")
    with (path / PIN).open("x", encoding="utf-8") as stream:
        json.dump({"reason": reason, "confirmed_utc": datetime.now(timezone.utc).isoformat()},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="Delete the excess runs shown by the plan")
    action.add_argument("--pin", type=Path, metavar="RUN", help="Mark a user-confirmed important run")
    parser.add_argument("--reason", help="Reason and confirmation for --pin")
    args = parser.parse_args()
    if args.pin is not None and (not args.reason or not args.reason.strip()):
        parser.error("--pin requires --reason")
    try:
        with mutation_lock(ROOT) if args.apply or args.pin is not None else nullcontext():
            if args.pin is not None:
                path = ROOT / args.pin
                pin_run(ROOT, path, args.reason)
                print("PINNED", path.relative_to(ROOT))
            else:
                entries = list(plan(ROOT))
                for path, decision in entries:
                    if args.apply and decision == "DELETE":
                        remove_run(ROOT, path)
                        decision = "DELETED"
                    print(decision, path.relative_to(ROOT))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
