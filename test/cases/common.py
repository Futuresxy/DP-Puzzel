"""Deterministic logical-element stimulus helpers, independent of CModel internals."""
from cases.import_legacy import request_from_elements
from reference.exact import DTYPES, FORMATS


def make(mode,k=16,a=None,b=None,c=0,sa=None,sb=None,ident=0,last=False,metadata=None):
    dt=DTYPES[mode]; _,eb,fb,bias,_,group_n=FORMATS[dt]; n=k//4*group_n
    one=1 if dt==10 else 4 if dt==9 else bias<<fb
    if dt==0: one<<=13
    grain=16 if dt==8 else 64 if dt==9 else 32
    ns=(n+grain-1)//grain if 3<=dt<=9 else 0
    default_scale=56 if dt==8 else 192 if dt==9 else 127
    if metadata is None:
        metadata=([0]*(n//4),[0]*(n//4),[0]*(n//8),[0]*(n//8)) if dt==9 else ((),(),(),())
    return request_from_elements(mode,[one]*n if a is None else a,[one]*n if b is None else b,c,
        [default_scale]*ns if sa is None else sa,[default_scale]*ns if sb is None else sb,
        *metadata,ident=ident,last=last,k_fp16=k)


def random_request(mode,rng,k=16,ident=0):
    dt=DTYPES[mode]; _,eb,fb,_,_,group_n=FORMATS[dt]; n=k//4*group_n
    def raw():
        if dt==10: return rng.randrange(256)
        if dt==9: return rng.randrange(16)
        bits=rng.randrange(1<<(1+eb+fb))
        return bits<<13 if dt==0 else bits
    grain=16 if dt==8 else 64 if dt==9 else 32
    ns=(n+grain-1)//grain if 3<=dt<=9 else 0
    scales=lambda:[rng.randrange(128 if dt==8 else 256) for _ in range(ns)]
    meta=tuple([rng.randrange(2) for _ in range(n//d)] for d in (4,4,8,8)) if dt==9 else None
    return make(mode,k,[raw() for _ in range(n)],[raw() for _ in range(n)],rng.getrandbits(32),
                scales(),scales(),ident,ident%7==0,meta)
