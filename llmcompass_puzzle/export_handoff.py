"""Export a minimal, source-complete workspace with pinned upstream and reviewed evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
REVIEWED_RUNS = ('moe-system-20261113-v3', 's1-reference-20261113-v3', 'system-audit-20261113-v4')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')


def relative(path):
    path = Path(path)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'Expected workspace-relative path: {path}')
    return path


def verify(root):
    manifest = read(root/'handoff_manifest.json')
    for name, expected in manifest['files_sha256'].items():
        path = root/relative(name)
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f'Handoff file missing or changed: {name}')
    return {'verified_files': len(manifest['files_sha256']), 'scope': manifest['scope']}


def export(output, include_runs=True):
    from .backend import upstream
    upstream()  # Verify audited upstream hashes and revisions before exporting.
    output = output.resolve()
    if output.exists() or output.with_suffix(output.suffix+'.sha256').exists():
        raise ValueError('Export path must be new')
    files = set()
    def add(path):
        path = relative(path)
        if not (ROOT/path).is_file():
            raise FileNotFoundError(path)
        files.add(path)
    def tree(base, excluded=()):
        for path in (ROOT/base).rglob('*'):
            parts = path.relative_to(ROOT/base).parts
            if path.is_file() and not any(p in (*excluded, '__pycache__', '.git') for p in parts) and path.suffix != '.pyc':
                add(path.relative_to(ROOT))
    tree(Path('llmcompass_puzzle'), ('upstream', 'runs', 'exports', '.venv'))
    for path in ['ratio_dse/__init__.py','ratio_dse/common.py','ratio_dse/formats.py',
                 'ratio_dse/README.md','ratio_dse/configs/area/dp_n12_20261112.lock.json',
                 'dependencies/llmcompass.json','dependencies/deepscaletool.json',
                 'dependencies/quantization_sources.json','paper/data/evidence/model_sources.json',
                 'paper/data/process_normalization/table_inputs.json',
                 'hw/data/dp_latest_area_power_20261112.csv','hw/data/dp_latest_area_power_20261112.md',
                 '.skill/academic-figures/assets/paper.mplstyle']:
        add(path)
    tree(Path('ratio_dse/area_model'))
    lock = read(ROOT/'ratio_dse/configs/area/dp_n12_20261112.lock.json')
    optional_evidence = []
    for kind, entries in lock['sources'].items():
        for entry in entries:
            add(entry['path'])
            if sha(ROOT/entry['path']) != entry['sha256']:
                raise ValueError(f"Evidence changed: {entry['path']}")
            if kind == 'dc':
                optional_evidence += [str(Path(r['run'])/'summary.json') for r in read(ROOT/entry['path'])['records']]
            if kind == 'power':
                optional_evidence += [r['audit_path'] for r in read(ROOT/entry['path'])['results']]
    missing = []
    for name in optional_evidence:
        path = relative(name)
        if (ROOT/path).is_file():add(path)
        else:missing.append(str(path))
    cfg = read(HERE/'configs/moe_system_study.json')
    for model in cfg['models']:
        add(f'paper/data/inputs/models/{model}/inference/config.json')
    for path in (ROOT/'paper/figures').glob('llmcompass_*.pdf'):
        add(path.relative_to(ROOT))
    for source in read(ROOT/'dependencies/quantization_sources.json')['sources']:
        for file in source['files']:
            add(file['path'])
            if sha(ROOT/file['path']) != file['sha256']:
                raise ValueError(f"Quantization audit source changed: {file['path']}")
    if include_runs:
        for name in REVIEWED_RUNS:
            path = Path('llmcompass_puzzle/runs')/name
            if not (ROOT/path/'manifest.json').is_file() and not (ROOT/path/'area/manifest.json').is_file():
                raise FileNotFoundError(f'Reviewed run not found: {path}; use --without-runs for a compact source export')
            tree(path)
    upstream_lock = read(ROOT/'dependencies/llmcompass.json')
    upstream_root = ROOT/upstream_lock['directory']
    # Copy only existing tracked sparse-checkout files, never Git credentials/history or caches.
    upstream_files = {}
    if (upstream_root/'.puzzle-source.json').is_file() and not (upstream_root/'.git').exists():
        upstream_files = read(upstream_root/'.puzzle-source.json')['files_sha256']
        for name in upstream_files:add(Path(upstream_lock['directory'])/name)
    else:
        for suffix in ['', *[s['path'] for s in upstream_lock['submodules']]]:
            repo = upstream_root/suffix
            subprocess.run(['git','-C',str(repo),'diff-index','--cached','--quiet','HEAD'],check=True)
            entries = subprocess.check_output(['git','-C',str(repo),'ls-files','--stage','-z']).decode().split('\0')
            for item in filter(None, entries):
                meta, name = item.split('\t',1)
                mode, object_id, _ = meta.split()
                src = repo/name
                if mode == '160000' or not src.is_file():continue
                if src.is_symlink():raise ValueError(f'Unexpected upstream source symlink: {src}')
                actual = subprocess.check_output(['git','hash-object','--no-filters',str(src)],text=True).strip()
                if actual != object_id:raise ValueError(f'Uncommitted upstream edit: {src}')
                rel = (Path(suffix)/name).as_posix()
                upstream_files[rel] = sha(src)
                add(src.relative_to(ROOT))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='llmcompass-handoff-') as directory:
        bundle = Path(directory)/'llmcompass_puzzle_workspace'
        bundle.mkdir()
        for rel in sorted(files):
            target = bundle/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/rel,target)
        write(bundle/upstream_lock['directory']/'.puzzle-source.json', {
            'schema_version':1,'commit':upstream_lock['commit'],
            'submodules':{s['path']:s['commit'] for s in upstream_lock['submodules']},
            'files_sha256':upstream_files,'kind':'verified sparse source export; no Git metadata'})
        (bundle/'README.md').write_text('# LLMCompass-Puzzle integrated workspace\n\n'
            'Start with [llmcompass_puzzle/handoff.md](llmcompass_puzzle/handoff.md).\n\n'
            'Run commands from this workspace root. Upstream source, measured-cost summaries, model configs, '
            'adapters and reviewed results are included. Create a new Python environment; no GPU is required.\n')
        write(bundle/'handoff_manifest.json',{
            'schema_version':1,'scope':'integrated source and evidence workspace; not EDA replay or model weights',
            'source_base_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip() if (ROOT/'.git').exists() else 'portable_workspace',
            'included_reviewed_runs':list(REVIEWED_RUNS) if include_runs else [],
            'missing_optional_eda_summaries':missing,
            'files_sha256':{str(p.relative_to(bundle)):sha(p) for p in sorted(bundle.rglob('*')) if p.is_file()}})
        verified = verify(bundle)
        def portable_owner(info):
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            return info
        with tarfile.open(output,'w:gz') as archive:
            archive.add(bundle,arcname=bundle.name,filter=portable_owner)
    output.with_suffix(output.suffix+'.sha256').write_text(f'{sha(output)}  {output.name}\n')
    return verified | {'archive':str(output),'bytes':output.stat().st_size,'sha256':sha(output)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path)
    group.add_argument('--verify',type=Path,help='Verify an extracted workspace before making changes')
    parser.add_argument('--without-runs',action='store_true',help='Keep compact records but omit full reviewed run tables')
    args=parser.parse_args()
    print(json.dumps(verify(args.verify.resolve()) if args.verify else export(args.output,not args.without_runs),indent=2))


if __name__=='__main__':main()
