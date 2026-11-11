"""Finite-window v1.8 reference, separate from the immutable exact mathematical golden.

Uses rational arithmetic rather than CModel intermediate layouts. Legacy profiles
retain exact.py's original finite-window policy; limited=False always stays exact.
"""
from . import exact
from .exact import F, unpack, multiply, sum_values, scale, power, quantize, floor_log2, fp32


def reference(request,config,limited=False):
    if config.get('architecture_v19', False):
        # v1.9 mixes frontend implementations, not numerical coordinates. Use
        # the active mathematical length; poisoned inactive slots are excluded.
        profile = config.get('frontend', 'multi')
        datatype = request['a_datatype']
        active_k = config['k_fp16']
        if profile in ('t8h16q32e96', 't8h16q32e128', 't8h16q64e128', 't8h16q64e128_opt'):
            extension_active = 7 <= datatype <= 9 or (
                profile in ('t8h16q64e128', 't8h16q64e128_opt') and 3 <= datatype <= 6)
            active_k = (24 if profile == 't8h16q32e96' else 32) if extension_active else 16
        config = config | dict(frontend='multi', k_fp16=active_k, legacy_multi=False)
    if not limited or config.get('frontend', 'multi') != 'multi' or config.get('legacy_multi', False):
        return exact.reference(request, config, limited)
    sides,cv,group_n=unpack(request,config['k_fp16']); dt=request['a_datatype']
    groups=[]; bound=F(0); local_loss=False; global_loss=False
    for g in range(config['k_fp16']//4):
        pairs=list(zip(sides[0][g*group_n:(g+1)*group_n],sides[1][g*group_n:(g+1)*group_n]))
        products=[multiply(a[0],b[0]) for a,b in pairs]
        scale_a=scale(int(request['a_scale'],16)>>(g*8)&255,request['a_scale_datatype'])
        scale_b=scale(int(request['b_scale'],16)>>(g*8)&255,request['b_scale_datatype'])
        pair_scale=multiply(scale_a,scale_b)
        local_bound=F(0)
        if limited and dt<=6:
            exps=[a[1]+b[1] for (a,b),p in zip(pairs,products) if p.kind=='finite' and p.value]
            unit=power(max(exps,default=0)-(config['local_shift_mag_width']-2))
            new=[]
            for p in products:
                q,lost=quantize(p,unit); new.append(q); local_loss|=lost
                if lost: local_bound+=unit
            products=new
        group=multiply(sum_values(products),pair_scale)
        groups.append(group)
        if pair_scale.kind=='finite': bound+=local_bound*abs(pair_scale.value)
    terms=groups+[cv]
    if limited and dt!=10:
        exps=[floor_log2(abs(v.value)) for v in terms if v.kind=='finite' and v.value]
        if (config.get('frontend', 'multi') == 'multi' and not config.get('legacy_multi', False)
                and cv.kind == 'finite' and cv.value and abs(cv.value) < power(-126)):
            exps.append(-126)  # v1.8 C has no LZD; preserve its raw subnormal coordinate.
        unit=power(max(exps,default=0)-(config['global_signed_align_width']-2))
        new=[]
        for v in terms:
            q,lost=quantize(v,unit); new.append(q); global_loss|=lost
            if lost: bound+=unit
        terms=new
    value=sum_values(terms)
    bits=(int(value.value)%(1<<32)) if dt==10 else fp32(value)
    return dict(bits=bits,value=value,bound=bound,local_loss=local_loss,global_loss=global_loss)

