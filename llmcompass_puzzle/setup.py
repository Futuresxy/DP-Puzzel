"""Prepare the pinned, CPU-only reference environment; leave existing source untouched."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent


def call(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify existing checkout and environment without downloading")
    parser.add_argument("--wheelhouse", type=Path, help="Install only from a prepared wheel directory; no network")
    args = parser.parse_args()
    lock = json.loads((ROOT / "dependencies/llmcompass.json").read_text())
    source = ROOT / lock["directory"]
    python = HERE / ".venv/bin/python"
    if not args.check:
        if not source.exists():
            if args.wheelhouse:
                parser.error('Offline install requires the portable upstream source snapshot or a prepared checkout.')
            source.parent.mkdir(parents=True, exist_ok=True)
            call("git", "clone", "--filter=blob:none", "--no-checkout", lock["url"], source)
            call("git", "-C", source, "sparse-checkout", "set", "hardware_model", "software_model",
                 "cost_model", "configs", "design_space_exploration", "docs")
            call("git", "-C", source, "checkout", "--detach", lock["commit"])
        portable = (source / '.puzzle-source.json').is_file() and not (source / '.git').exists()
        if portable:
            call(sys.executable, '-c', 'from llmcompass_puzzle.backend import upstream; upstream()')
        else:
            head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            if head != lock["commit"]:
                parser.error("Existing checkout has a different commit; refusing to change it.")
            for sub in lock["submodules"]:
                call("git", "-C", source, "submodule", "update", "--init", "--", sub["path"])
        if not python.exists():
            call(sys.executable, "-m", "venv", HERE / ".venv")
        offline = ['--no-index', '--find-links', args.wheelhouse.resolve()] if args.wheelhouse else []
        call(python, "-m", "pip", "install", *offline, "-r", HERE / "requirements-cpu.txt")
    call(python, "-c", "from llmcompass_puzzle.backend import upstream; upstream(); "
         "import json, importlib.metadata as m; "
         "lock=json.load(open('dependencies/llmcompass.json')); "
         "bad={k:(m.version(k),v) for k,v in lock['cpu_runtime_packages'].items() if m.version(k)!=v}; "
         "assert not bad, bad; print('Pinned sources and CPU packages verified.')")


if __name__ == "__main__":
    main()
