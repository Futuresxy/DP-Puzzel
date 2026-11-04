"""Immutable source snapshots for reproducible hand-written RTL simulation.

This does not elaborate a technology netlist or authorize PPA. Parameters and
verified scopes live in each regression report; each snapshot is content-addressed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]

def snapshot(implementation):
    base=ROOT/'src/verilog'
    source_list=base/('files.f' if implementation=='verilog' else 'systemverilog/files.f')
    sources=[ROOT/line for line in source_list.read_text().splitlines() if line and not line.startswith('+')]
    # The plain-Verilog TB also consumes this same encoding header in SV runs.
    sources+=list(sorted((base/'parameter').glob('*.vh')))
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    fingerprint=hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode()).hexdigest()
    export_id=f'DP_{implementation}_{fingerprint[:16]}'
    dest=ROOT/'hw/rtl'/export_id
    if not dest.exists():
        dest.mkdir(parents=True)
        exported={}
        for p in sources:
            rel=p.relative_to(ROOT); target=dest/'src'/rel; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text('// RTL_ID: '+export_id+'\n'+p.read_text())
            exported[str(Path('src')/rel)]=hashlib.sha256(target.read_bytes()).hexdigest()
        canonical=['+incdir+src/src/verilog/parameter']+[str(Path('src')/p.relative_to(ROOT)) for p in sources if p.suffix in ('.v','.sv')]
        (dest/'files.f').write_text('\n'.join(canonical)+'\n')
        (dest/'manifest.json').write_text(json.dumps(dict(schema_version=1,export_id=export_id,
            implementation=implementation,source_fingerprint=fingerprint,source_sha256=source_hashes,
            exported_sha256=exported,status='generated',verified_scopes=[],
            created_utc=datetime.now(timezone.utc).isoformat(),top='dp_top',
            specialization='parameterized source snapshot; parameters recorded per simulation',ppa_eligible=False),indent=2)+'\n')
        (dest/'README.md').write_text(f'# {export_id}\n\nFrozen hand-written RTL sources for DP v1.4.\n\n'
            'Created by `test/adapters/rtl.py`; no flattening or source editing. '
            'Compile `files.f` relative to this export directory. Parameters and verified scopes are in the regression report. '
            'No DC, timing or power analysis was performed.\n')
    manifest=json.loads((dest/'manifest.json').read_text())
    if manifest['source_sha256']!=source_hashes: raise RuntimeError('snapshot source collision')
    for rel,digest in manifest['exported_sha256'].items():
        if hashlib.sha256((dest/rel).read_bytes()).hexdigest()!=digest:
            raise RuntimeError(f'modified snapshot: {dest/rel}')
    # Build-tool adapter only; canonical manifest/list above use portable paths.
    resolved=[]
    for line in (dest/'files.f').read_text().splitlines():
        resolved.append('+incdir+'+str(dest/line[len('+incdir+'):]) if line.startswith('+incdir+') else str(dest/line))
    build_list=ROOT/'test/runs/verilog'/f'{export_id}.f'
    build_list.parent.mkdir(parents=True,exist_ok=True); build_list.write_text('\n'.join(resolved)+'\n')
    return dest,build_list


def record_validation(dest,scopes,test_fingerprint):
    path=dest/'manifest.json'; manifest=json.loads(path.read_text())
    # Recheck exactly the simulated inputs before assigning any passing status.
    for rel,digest in manifest['exported_sha256'].items():
        if hashlib.sha256((dest/rel).read_bytes()).hexdigest()!=digest: raise RuntimeError('snapshot modified during verification')
    previous=manifest.get('verified_scopes',[])
    keys={(r['simulator'],r['implementation'],r['name'],r['k_fp16'],r['local_width'],r['global_width']) for r in scopes}
    combined=[r for r in previous if (r['simulator'],r['implementation'],r['name'],r['k_fp16'],r['local_width'],r['global_width']) not in keys]+scopes
    manifest.setdefault('validation_runs',[]).append(dict(test_fingerprint=test_fingerprint,scopes=scopes))
    manifest.update(status='passed',verified_scopes=combined,test_fingerprint=test_fingerprint,
                    validated_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(manifest,indent=2)+'\n')
