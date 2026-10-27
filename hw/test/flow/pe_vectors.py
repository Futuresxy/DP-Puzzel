"""Logical, format/K keyed vectors and the six LAB1 physical profiles.

Raw element encodings are stored in zero-extended 16-bit text containers.
Physical packing and scale-slot placement belong to the SystemVerilog driver.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT/'hw/test/data/petile_ratio'
FORMATS = {
 'bf16': (7,2,1,'H'), 'fp16': (8,2,1,'H'),
 'mxfp8_e5m2': (6,2,2,'Q'), 'mxfp8_e4m3': (5,2,2,'Q'),
 'mxfp6_e3m2': (4,2,2,'Q'), 'mxfp6_e2m3': (3,2,2,'Q'),
 'mxfp4_e2m1': (1,2,4,'E'), 'nvfp4': (0,1,4,'E'), 'hif4': (2,3,4,'E')}
PROFILES = {
 'k_1_2_4': ('k','K_PE_H16Q32E64',[('HQE',16)]),
 'k_1_2_6': ('k','K_PE_H16Q32E96',[('HQE',16),('E',8)]),
 'k_1_2_8': ('k','K_PE_H16Q32E128',[('HQE',16),('E',16)]),
 'k_1_4_8': ('k','K_PE_H16Q64E128',[('HQE',16),('QE',16)]),
 'mn_e_g4': ('mn','MN_PE_H0Q0E64',[('E',16)]),
 'mn_qe_g4': ('mn','MN_PE_H0Q32E64',[('QE',16)])}
MERGED_DATASET = 'correct_961'
MERGE_COMPONENTS = (
 ('batch64_random',64), ('batch128_mixed_random',128),
 ('batch256_deepseek_ai_load',256), ('batch512_ai_load',512), ('ones',1))
DEFAULT_DATASETS = [MERGED_DATASET]
EXACT_GOLDEN_MODEL = 'integer_dyadic_dot_plus_c_rne_fp32_v1'


def native_k(profile, fmt):
 _,_,lanes,family=FORMATS[fmt]
 return sum(words*lanes for kinds,words in PROFILES[profile][2] if family in kinds)


def read_hex(path, width, count):
 tokens=path.read_text().splitlines()
 if len(tokens)!=count: raise ValueError(f'{path}: expected {count} rows, got {len(tokens)}')
 values=[]
 for i,t in enumerate(tokens):
  if not t or any(c not in '0123456789abcdefABCDEF' for c in t) or len(t)>(width+3)//4:
   raise ValueError(f'{path}:{i+1}: invalid HEX')
  v=int(t,16)
  if v>=1<<width: raise ValueError(f'{path}:{i+1}: overflow')
  values.append(v)
 return values


def fields(meta):
 return [meta[k] for k in ['txn_count','logical_k','a_data_type','b_data_type','a_sf_type',
        'b_sf_type','c_type','out_type','rm','a_scale_count','b_scale_count','group0_count','group1_count']]


def row_width(meta):
 return 2+2*meta['logical_k']+meta['a_scale_count']+meta['b_scale_count']+2*(meta['group0_count']+meta['group1_count'])


def validate_case(directory):
 m=json.loads((directory/'case.json').read_text())
 dtype,sft,lanes,fam=FORMATS[m['format']]
 k=m['logical_k'];n=m['txn_count']
 if (m['schema_version']!='dp_pe_vectors_v2' or type(n) is not int or n<=0 or k<=0
     or m['a_data_type']!=dtype or m['b_data_type']!=dtype
     or m['a_sf_type']!=sft or m['b_sf_type']!=sft
     or m['c_type']!=0 or m['out_type']!=0 or m['rm']!=0
     or m['golden_model'] not in ('fp64_dequant_dot_plus_c_v1',EXACT_GOLDEN_MODEL)
     or m['acceptance_policy']!=('fp32_steps_le2_special_exact_v1' if m['golden_model']==EXACT_GOLDEN_MODEL else 'petile_precision_v1')):
  raise ValueError(f'{directory}: unsupported metadata')
 sf=0 if fam=='H' else ((k+63)//64 if dtype==2 else k//(16 if dtype==0 else 32))
 g0,g1=(k//4,k//8) if dtype==2 else (0,0)
 if (m['a_scale_count'],m['b_scale_count'],m['group0_count'],m['group1_count'])!=(sf,sf,g0,g1):
  raise ValueError(f'{directory}: scale/group shape mismatch')
 if m.get('kind')=='merged_fixed_datasets':
  segments=m.get('segments',[]);offset=0
  if m['dataset']!=MERGED_DATASET or n!=961 or len(segments)!=len(MERGE_COMPONENTS):
   raise ValueError('invalid merged case identity/length')
  for segment,(dataset,count) in zip(segments,MERGE_COMPONENTS):
   if (segment['dataset']!=dataset or segment['count']!=count
       or segment['start']!=offset or segment['stop']!=offset+count
       or segment['include_in_precision_rate'] is not (dataset!='ones')
       or segment['require_bit_exact'] is not (dataset=='ones')):
    raise ValueError('invalid merged segment boundary or precision policy')
   offset+=count
  if offset!=n or m.get('precision_txn_count')!=960:
   raise ValueError('invalid merged precision denominator')
 exact = m['golden_model']==EXACT_GOLDEN_MODEL
 if exact:
  sys.path.insert(0,str(ROOT/'hw/test/vectors'))
  from exact_dot import FP32,Operand,decode_binary,dot_product,exact_sum,round_fp32,serialize
  from normal_scope import NORMAL_CONTRACT,NORMAL_DATASET,normal_scope_violations
  sampling_scope=m.get('sampling_scope','stress')
  if sampling_scope not in ('normal','stress'):
   raise ValueError('unknown exact random sampling scope')
  if sampling_scope=='normal' and m.get('normal_scope_contract')!=NORMAL_CONTRACT:
   raise ValueError('unrecognized normal input scope contract')
  expected_dataset=NORMAL_DATASET if sampling_scope=='normal' else 'random_1600'
  expected_segments=[('ab_scale_random',1024,True,False),('special_directed',64,False,True),
                     ('c_stratified_random',512,True,False)]
  if (m.get('kind')!='random_exact_1600' or m['dataset']!=expected_dataset or n!=1600
      or m.get('precision_txn_count')!=1536 or len(m.get('segments',[]))!=3
      or len(m.get('exact_results',[]))!=n or len(m.get('scenario_by_transaction',[]))!=n):
   raise ValueError('invalid exact random corpus identity/count')
  offset=0
  for s,(dataset,count,precision,bit_exact) in zip(m['segments'],expected_segments):
   if (s['dataset'],s['count'],s['start'],s['stop'],s['include_in_precision_rate'],s['require_bit_exact'])!=(dataset,count,offset,offset+count,precision,bit_exact):
    raise ValueError('invalid exact random segment contract')
   offset+=count
 elif m.get('kind')=='random_exact_1600':
  raise ValueError('exact random cases require the exact golden model')
 goldens=read_hex(directory/'golden.txt',32,n)
 bits=16 if lanes==1 else 6 if dtype in (3,4) else 8 if lanes==2 else 4
 with (directory/'inputs.txt').open() as f:
  if f.readline().strip()!='PE_VECTORS_V2': raise ValueError('bad vector magic')
  if [int(x) for x in f.readline().split()]!=fields(m): raise ValueError('header disagrees with case.json')
  count=0
  for line in f:
   ts=line.split()
   if len(ts)!=row_width(m): raise ValueError(f'{directory}: row {count} field count')
   if any(not t or any(c not in '0123456789abcdefABCDEF' for c in t) for t in ts):
    raise ValueError(f'{directory}: invalid HEX token')
   vals=[int(t,16) for t in ts]
   if vals[0]!=count or vals[1]>0xffffffff: raise ValueError('transaction ID/C mismatch')
   if any(v>=1<<bits for v in vals[2:2+2*k]): raise ValueError('element raw code exceeds format')
   if any(v>255 for v in vals[2+2*k:2+2*k+2*sf]): raise ValueError('scale raw code exceeds 8 bits')
   if any(v>1 for v in vals[2+2*k+2*sf:]): raise ValueError('group bits exceed 1 bit')
   if exact:
    start=2+2*k
    a_scale,b_scale=vals[start:start+sf],vals[start+sf:start+2*sf]
    start+=2*sf
    a_g0,b_g0=vals[start:start+g0],vals[start+g0:start+2*g0]
    start+=2*g0
    a=Operand(vals[2:2+k],a_scale,a_g0,vals[start:start+g1])
    b=Operand(vals[2+k:2+2*k],b_scale,b_g0,vals[start+g1:start+2*g1])
    reference=exact_sum((dot_product(m['format'],a,b),decode_binary(FP32,vals[1])))
    if count>=n or serialize(reference)!=m['exact_results'][count] or round_fp32(reference)!=goldens[count]:
     raise ValueError('exact reference/golden does not match input encodings')
    if sampling_scope=='normal' and not 1024<=count<1088 and normal_scope_violations(m['format'],a,b,vals[1]):
     raise ValueError('ordinary input violates the declared normal cancellation scope')
   count+=1
  if count!=n: raise ValueError(f'{directory}: missing/extra transactions {count}/{n}')
 return m
