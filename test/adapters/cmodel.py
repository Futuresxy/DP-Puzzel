"""Shared packed-port vectors and a thin JSON-lines CModel transport.

The canonical input text is directly readable by a future SV $fscanf driver.
No numerical conversions occur in this adapter.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ("id", "a_datatype", "b_datatype", "c_datatype", "a_scale_datatype",
          "b_scale_datatype", "last", "a", "b", "c", "a_scale", "b_scale",
          "a_e1", "a_e2", "b_e1", "b_e2")
DEFAULT_CONFIG = dict(k_fp16=16, local_shift_mag_width=28,
                      global_signed_align_width=40, post_scale_norm_extra_stage=0)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_inputs(path, requests, k_fp16):
    widths = dict(a=k_fp16*4, b=k_fp16*4, c=8, a_scale=k_fp16//2,
                  b_scale=k_fp16//2, a_e1=k_fp16//4, b_e1=k_fp16//4,
                  a_e2=(k_fp16//2+3)//4, b_e2=(k_fp16//2+3)//4)
    lines = ["DP_INPUTS_V1", f"{len(requests)} {k_fp16}"]
    for r in requests:
        lines.append(" ".join(str(int(r[f])) if i<7 else
                              f"{int(r[f],16):0{widths[f]}x}" for i,f in enumerate(FIELDS)))
    Path(path).write_text("\n".join(lines)+"\n")


def read_inputs(path):
    lines=Path(path).read_text().splitlines()
    if lines[0]!="DP_INPUTS_V1":
        raise ValueError("bad input magic")
    count,k=map(int,lines[1].split())
    requests=[]
    for line in lines[2:]:
        values=line.split()
        if len(values)!=len(FIELDS):
            raise ValueError("bad port record width")
        r={f:int(v) if i<7 else v for i,(f,v) in enumerate(zip(FIELDS,values))}
        if r['last'] not in (0,1):
            raise ValueError("last must be 0/1")
        r['last']=bool(r['last']); requests.append(r)
    if len(requests)!=count or k not in (4,8,16):
        raise ValueError("invalid vector dimensions")
    return k,requests


def invoke(commands, config=None, trace=False, allow_errors=False, run_dir=None, binary=None):
    run=Path(run_dir or ROOT/'test/runs/cmodel'); run.mkdir(parents=True,exist_ok=True)
    cfg=DEFAULT_CONFIG | (config or {})
    config_path=run/'config.json'; config_path.write_text(json.dumps(cfg,sort_keys=True,indent=2)+'\n')
    exe=Path(binary or ROOT/'src/cmodel/build/dp_cmodel_cli')
    argv=[str(exe),'--config',str(config_path)] + (['--trace'] if trace else [])
    proc=subprocess.run(argv,input=''.join(json.dumps(x)+'\n' for x in commands),
                        text=True,capture_output=True,check=False)
    if proc.returncode and not allow_errors:
        raise RuntimeError(f'CModel failed ({proc.returncode}): {proc.stderr}\n{proc.stdout[:3000]}')
    results=[json.loads(line) for line in proc.stdout.splitlines()]
    if len(results)!=len(commands):
        raise RuntimeError(f'CModel response count mismatch: {proc.stderr}')
    return results


def evaluate(requests, **kwargs):
    return invoke([dict(op='eval',request=r) for r in requests],**kwargs)
