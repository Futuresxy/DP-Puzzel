"""Independent mathematical and finite-window references using Fraction.

This code does not import CModel decode/rounding code or model-derived goldens.
The finite-window oracle quantizes real dyadic values; it does not reproduce
the C++ fixed-container layouts, multiplier reconstruction, or bidirectional mux.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from functools import reduce
import math
import struct

# Interface enumeration, external fields. Internal E5M3 recoding is not used here.
FORMATS={0:('tf32',8,10,127,32,2),1:('fp16',5,10,15,16,4),
         2:('bf16',8,7,127,16,4),3:('mxfp8_e4m3',4,3,7,8,8),
         4:('mxfp8_e5m2',5,2,15,8,8),5:('mxfp6_e3m2',3,2,3,8,8),
         6:('mxfp6_e2m3',2,3,1,8,8),7:('mxfp4_e2m1',2,1,1,4,16),
         8:('nvfp4',2,1,1,4,16),9:('hif4',0,2,0,4,16),
         10:('int8',0,0,0,8,8)}
DTYPES={v[0]:k for k,v in FORMATS.items()}


def power(e): return F(2)**e


@dataclass(frozen=True)
class Value:
    value: F=F(0)
    kind: str='finite'
    negative: bool=False
    invalid: bool=False


def finite(value, negative_zero=False):
    return Value(F(value),'finite',value<0 or (value==0 and negative_zero))


def binary(raw,eb,fb,bias,ieee=True,e4m3=False):
    negative=bool(raw>>(eb+fb)&1); exponent=raw>>fb&((1<<eb)-1); frac=raw&((1<<fb)-1)
    if exponent==(1<<eb)-1:
        if (ieee and frac) or (e4m3 and frac==(1<<fb)-1):
            return Value(kind='nan',invalid=ieee and not bool(frac&(1<<(fb-1)))),0
        if ieee:
            return Value(kind='inf',negative=negative),0
    e=max(exponent,1)-bias
    coefficient=frac+((1<<fb) if exponent else 0)
    return finite((-1 if negative else 1)*coefficient*power(e-fb),negative),e


def multiply(a,b):
    invalid=a.invalid or b.invalid
    invalid |= ((a.kind=='inf' and b.kind=='finite' and b.value==0) or
                (b.kind=='inf' and a.kind=='finite' and a.value==0))
    if a.kind=='nan' or b.kind=='nan' or invalid:
        return Value(kind='nan',invalid=invalid)
    negative=a.negative!=b.negative
    if a.kind=='inf' or b.kind=='inf':
        return Value(kind='inf',negative=negative)
    return finite(a.value*b.value,negative)


def add(a,b):
    invalid=a.invalid or b.invalid or (a.kind==b.kind=='inf' and a.negative!=b.negative)
    if a.kind=='nan' or b.kind=='nan' or invalid:
        return Value(kind='nan',invalid=invalid)
    if a.kind=='inf': return a
    if b.kind=='inf': return b
    return finite(a.value+b.value,a.value==0 and b.value==0 and a.negative and b.negative)


def sum_values(xs):
    # Preserve invalid from operations even when another term already has qNaN.
    xs=list(xs)
    signs={x.negative for x in xs if x.kind=='inf'}
    result=reduce(add,xs)
    if len(signs)==2:
        return Value(kind='nan',invalid=True)
    return result


def scale(raw,kind):
    if kind==0: return finite(1)
    if kind==1: return Value(kind='nan') if raw==255 else finite(power(raw-127))
    if kind==2: return binary(raw,4,3,7,False,True)[0]
    return Value(kind='nan') if raw==255 else finite(F(4+(raw&3),4)*power((raw>>2)-48))


def unpack(request,k_fp16):
    dt=request['a_datatype']; _,eb,fb,bias,storage,group_n=FORMATS[dt]
    count=k_fp16//4*group_n; sides=[]
    for side in ('a','b'):
        data=int(request[side],16); e1=int(request[f'{side}_e1'],16); e2=int(request[f'{side}_e2'],16)
        vals=[]
        for i in range(count):
            raw=data>>(i*storage)&((1<<storage)-1)
            if dt==10:
                vals.append((finite(raw if raw<128 else raw-256),0))
            elif dt==9:
                exp=(e2>>(i//8)&1)
                v=F(raw&7,4)*power((e1>>(i//4)&1)+exp)
                vals.append((finite(-v if raw&8 else v,bool(raw&8)),exp))
            else:
                if dt==0: raw>>=13
                if dt in (5,6): raw>>=2
                vals.append(binary(raw,eb,fb,bias,dt in (0,1,2,4),dt==3))
        sides.append(vals)
    c_raw=int(request['c'],16)
    cv=finite(c_raw if c_raw<1<<31 else c_raw-(1<<32)) if dt==10 else binary(c_raw,8,23,127)[0]
    return sides,cv,group_n


def floor_log2(x):
    assert x>0
    e=x.numerator.bit_length()-x.denominator.bit_length()
    if x<power(e): e-=1
    return e


def quantize(v,unit):
    if v.kind!='finite': return v,False
    units=abs(v.value)//unit
    q=finite((-1 if v.negative else 1)*units*unit,v.negative)
    return q,q.value!=v.value


def rne_integer(v):
    q,r=divmod(v.numerator,v.denominator)
    return q+int(2*r>v.denominator or (2*r==v.denominator and q&1)),r!=0


def fp32(v):
    if v.kind=='nan': return 0x7fc00000
    sign=0x80000000 if v.negative else 0
    if v.kind=='inf': return sign|0x7f800000
    x=abs(v.value)
    if not x: return sign
    e=floor_log2(x)
    if e < -126:
        q,_=rne_integer(x/power(-149))
        return sign|q
    q,_=rne_integer(x/power(e-23))
    if q==1<<24: q>>=1; e+=1
    if e>127: return sign|0x7f800000
    return sign|((e+127)<<23)|(q-(1<<23))


def reference(request,config,limited=False):
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
        unit=power(max(exps,default=0)-(config['global_signed_align_width']-2))
        new=[]
        for v in terms:
            q,lost=quantize(v,unit); new.append(q); global_loss|=lost
            if lost: bound+=unit
        terms=new
    value=sum_values(terms)
    bits=(int(value.value)%(1<<32)) if dt==10 else fp32(value)
    return dict(bits=bits,value=value,bound=bound,local_loss=local_loss,global_loss=global_loss)


def fp64_tf32(request,config):
    sides,cv,_=unpack(request,config['k_fp16'])
    if any(v.kind!='finite' for side in sides for v,_ in side) or cv.kind!='finite':
        return None
    value=math.fsum([float(a[0].value)*float(b[0].value) for a,b in zip(*sides)]+[float(cv.value)])
    try: return struct.unpack('>I',struct.pack('>f',value))[0]
    except OverflowError: return 0xff800000 if value<0 else 0x7f800000


def ulp_distance(a,b):
    def ordered(x): return (0x80000000-(x&0x7fffffff)) if x>>31 else 0x80000000+x
    if (a&0x7f800000)==0x7f800000 or (b&0x7f800000)==0x7f800000:
        return 0 if a==b else None
    return abs(ordered(a)-ordered(b))


def error_bound_ok(bits,exact,limited):
    actual=binary(bits,8,23,127)[0]
    if actual.kind!='finite' or exact['value'].kind!='finite': return None
    rounding=power(-150) if abs(actual.value)<power(-126) else power(floor_log2(abs(actual.value))-24)
    return abs(actual.value-exact['value'].value)<=limited['bound']+rounding
