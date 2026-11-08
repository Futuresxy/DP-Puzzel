"""Analytical V4.1 GEMM work: kernel -> block -> text prefill/decode.

All work is integer FLOPs (2 per MAC), never time or hardware throughput.
Sequence-position sums are closed form, including pinned partial candidate
blocks. This module imports neither tensor libraries nor previous model tables.
"""
from collections import defaultdict
from dataclasses import dataclass, fields
import json
from pathlib import Path

PRECISIONS = ('FP32', 'BF16', 'FP8', 'FP4')
SOURCE_DIR = Path(__file__).resolve().parents[1]/'data/inputs/models/DeepSeek-V4.1-Flash'
SOURCE_REVISION = 'dba1be0a40aa45a94ad051997016db3960a90277'


def _integer(name, value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')


@dataclass(frozen=True)
class V41Config:
    dim: int = 5120
    n_heads: int = 64
    head_dim: int = 512
    rope_head_dim: int = 64
    q_lora_rank: int = 1280
    o_groups: int = 8
    o_lora_rank: int = 1024
    window_size: int = 128
    index_n_heads: int = 32
    index_head_dim: int = 128
    index_topk: int = 512
    candidate_topk_blocks: int = 2048
    candidate_block_size: int = 8
    n_routed_experts: int = 384
    n_activated_experts: int = 6
    n_shared_experts: int = 1
    moe_inter_dim: int = 2304
    hc_mult: int = 4
    vocab_size: int = 129280
    engram_max_ngram_size: int = 4
    engram_n_heads: int = 8
    engram_head_dim: int = 256
    n_layers: int = 40
    encoder_layers: int = 20
    max_context: int = 1048576
    compress_ratios: tuple = (0, 0)+(2,)*18+(1,)*20
    kv_source_layers: tuple = (2, 8, 14, 20)
    index_source_layers: tuple = (2, 8, 14, 20, 24, 28, 32, 36)
    engram_layer_ids: tuple = (1, 14)

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, tuple):
                if len(set(value)) != len(value) and field.name != 'compress_ratios':
                    raise ValueError('Duplicate layer IDs')
            else:
                _integer(field.name, value, 1)
        if len(self.compress_ratios) != self.n_layers or not 0 < self.encoder_layers < self.n_layers:
            raise ValueError('Invalid encoder/decoder layout')
        if self.n_heads % self.o_groups or self.n_activated_experts > self.n_routed_experts:
            raise ValueError('Invalid output groups or expert count')
        if self.candidate_topk_blocks*self.candidate_block_size < self.index_topk:
            raise ValueError('Candidate pool must accommodate the final index TopK')
        if self.engram_max_ngram_size < 2:
            raise ValueError('Engram needs at least order two')
        if any(r not in (0, 1, 2) for r in self.compress_ratios):
            raise ValueError('Compression ratios must be 0, 1 or 2')
        if not set(self.kv_source_layers) <= set(self.index_source_layers):
            raise ValueError('KV owners must also own an indexer')
        for name in ('kv_source_layers', 'index_source_layers', 'engram_layer_ids'):
            for i in getattr(self, name):
                _integer(name, i)
                if i >= self.n_layers:
                    raise ValueError('Layer ID outside backbone')
        owner = index_owner = None
        for i, ratio in enumerate(self.compress_ratios):
            if i in self.kv_source_layers:
                owner = i
            if i in self.index_source_layers:
                index_owner = i
            if not ratio and (i in self.kv_source_layers or i in self.index_source_layers):
                raise ValueError('SWA layer cannot own global KV/index')
            if ratio and (owner is None or index_owner is None or self.compress_ratios[owner] != ratio):
                raise ValueError('Compressed layer needs a compatible preceding owner')


def load_config(filename=None):
    """Map the fixed official config, excluding the three DSpark-only layers."""
    source = json.loads(Path(filename or SOURCE_DIR/'inference/config.json').read_text())
    names = {f.name for f in fields(V41Config)}
    values = {k:tuple(v) if isinstance(v, list) else v for k,v in source.items() if k in names}
    values['compress_ratios'] = values['compress_ratios'][:values['n_layers']]
    return V41Config(**values)


DEFAULT_CONFIG = load_config()


def floor_prefix(n, ratio=1, cap=None):
    """A_r,k(n) = sum(min(floor(t/r), k), t=1..n), in O(1)."""
    _integer('n', n); _integer('ratio', ratio, 1)
    if cap is not None:
        _integer('cap', cap)
    end = n if cap is None else min(n, ratio*cap)
    u,v = divmod(end, ratio)
    total = ratio*u*(u-1)//2+u*(v+1)
    return total if cap is None else total+(n-end)*cap


def visible_pairs(past, count, ratio=1, cap=None):
    _integer('past', past); _integer('count', count)
    return floor_prefix(past+count, ratio, cap)-floor_prefix(past, ratio, cap)


def candidate_prefix(n, ratio=1, blocks=2048, block_size=8):
    """Exact valid-position sum when the newest (possibly partial) block is pinned."""
    _integer('blocks', blocks, 1); _integer('block_size', block_size, 1)
    total = floor_prefix(n, ratio)
    m = max(0, n-(ratio*(blocks*block_size+1)-1))
    period = ratio*block_size
    u,v = divmod(m, period)
    return total-block_size*(period*u*(u+1)//2+(u+1)*v)


def candidate_pairs(past, count, ratio=1, blocks=2048, block_size=8, policy='pinned_blocks'):
    _integer('past', past); _integer('count', count)
    if policy == 'upper_bound':
        _integer('blocks', blocks, 1); _integer('block_size', block_size, 1)
        return visible_pairs(past, count, ratio, blocks*block_size)
    if policy != 'pinned_blocks':
        raise ValueError('Unknown candidate policy')
    return (candidate_prefix(past+count, ratio, blocks, block_size)
            -candidate_prefix(past, ratio, blocks, block_size))


def layer_schedule(config=DEFAULT_CONFIG):
    result = []
    owner = index_owner = -1
    for i, ratio in enumerate(config.compress_ratios):
        if i in config.kv_source_layers:
            owner = i
        if i in config.index_source_layers:
            index_owner = i
        mode = ('swa' if not ratio else 'full' if i in config.kv_source_layers else
                'reindex' if i in config.index_source_layers else 'reuse')
        result.append(dict(layer_id=i, stack='encoder' if i < config.encoder_layers else 'decoder',
                           mode=mode, ratio=ratio, kv_owner=owner if ratio else -1,
                           index_owner=index_owner if ratio else -1,
                           engram=i in config.engram_layer_ids))
    return result


def block_work(*, mode='reuse', ratio=2, past_tokens=0, query_tokens=1, batch=1,
               phase='prefill', local_past=None, config=DEFAULT_CONFIG, indexer='native',
               candidate_policy='pinned_blocks', include_mhc=True, include_engram=False,
               build_global=True, cache_only=False, layer_id=-1, segment='block'):
    """GEMM rows for one block, batched prefill or aggregated one-token decode.

    Non-owning modes assume shared KV/indices already exist. MoE assignment M
    and ragged pair sums count work, not dense hardware utilization. cache_only
    supports the independent decoder cache-build segment of the CED schedule.
    """
    for name,value,minimum in [('past_tokens',past_tokens,0),('query_tokens',query_tokens,0),('batch',batch,1)]:
        _integer(name,value,minimum)
    if phase not in ('prefill','decode') or indexer not in ('native','reference'):
        raise ValueError('Unknown phase/indexer')
    if candidate_policy not in ('pinned_blocks','upper_bound'):
        raise ValueError('Unknown candidate policy')
    if mode not in ('swa','full','reindex','reuse') or ratio not in (0,1,2) or (mode=='swa') != (ratio==0):
        raise ValueError('Use swa/ratio=0 or full/reindex/reuse with ratio=1/2')
    if cache_only and (mode != 'full' or not build_global):
        raise ValueError('Cache build needs Full ownership')
    local_past = past_tokens if local_past is None else local_past
    _integer('local_past',local_past)
    if not query_tokens:
        return []
    c = config
    d,H,hd,q,g,o = c.dim,c.n_heads,c.head_dim,c.q_lora_rank,c.o_groups,c.o_lora_rank
    f,a,s = c.moe_inter_dim,c.n_activated_experts,c.n_shared_experts
    Hi,ci,h = c.index_n_heads,c.index_head_dim,c.hc_mult
    P,T,M = past_tokens,query_tokens,batch*query_tokens
    meta = dict(phase=phase,segment=segment,layer_id=layer_id,mode=mode,ratio=ratio,
                past_tokens=P,query_tokens=T,local_past=local_past,batch=batch,indexer=indexer)
    rows = []

    def add(kernel, component, precision, m, n, k, repeat=1, formula='2*M*N*K*repeat',
            shape_kind='dense', operand=None, pairs=None, heads=None):
        flops = 2*m*n*k*repeat if pairs is None else 2*batch*heads*hd*pairs
        # Indexer uses ci rather than the main attention's hd.
        if pairs is not None and component=='indexer':
            flops = 2*batch*heads*ci*pairs
        native = precision=='FP4'
        accumulator = ('backend-dependent' if native or precision=='BF16' and pairs is None else 'FP32')
        rows.append(meta|dict(kernel=kernel,component=component,precision=precision,flops=flops,
            operand_format=operand or precision+' x '+precision,accumulator_precision=accumulator,
            precision_basis='paper native indexing' if native else 'released reference multiply dtype',
            m=m,n=n,k=k,repeat=repeat,shape_kind=shape_kind,valid_pairs=pairs,
            formula=formula))

    if not cache_only:
        for name,n,k in [('q_down',q,d),('q_up',H*hd,q),('swa_kv',hd,d),('o_final',d,g*o)]:
            add(name,'attention_projection','FP8',M,n,k)
        add('o_group','attention_projection','BF16',M,o,H*hd//g,g)
        swa = visible_pairs(local_past,T,1,c.window_size)
        glob = visible_pairs(P,T,ratio,c.index_topk) if ratio else 0
        for prefix,pairs in [('swa',swa)]+([('global',glob)] if ratio else []):
            add(prefix+'.qk','attention_'+prefix,'BF16',H,None,hd,batch*T,
                formula='2*B*H*c*U',shape_kind='ragged_qk',pairs=pairs,heads=H)
            add(prefix+'.pv','attention_'+prefix,'BF16',H,hd,None,batch*T,
                formula='2*B*H*c*U',shape_kind='ragged_pv',pairs=pairs,heads=H)
        for group,assignments,contract in [('routed',a*M,'W4A8'),('shared',s*M,'W8A8')]:
            for op,n,k in [('gate',f,d),('up',f,d),('down',d,f)]:
                add('moe.'+group+'.'+op,'moe_'+group,'FP8',assignments,n,k,
                    shape_kind='expert_assignments',operand=contract)
        add('moe.router','router','FP32',M,c.n_routed_experts,d)
        if include_mhc:
            for name in ('attention','ffn'):
                add('mhc.'+name,'mhc','FP32',M,h*(h+2),h*d)
        if include_engram:
            dim=(c.engram_max_ngram_size-1)*c.engram_n_heads*c.engram_head_dim
            add('engram.projection','engram','FP8',M,(h+1)*d,dim)

    if mode=='full' and build_global:
        add('global_kv.projection','global_kv','FP32' if ratio==2 else 'BF16',M,hd,d)
        if ratio==2:
            add('global_kv.pool_gate','global_kv','FP32',M,hd,d)
        entries=(P+T)//ratio-P//ratio
        add('index.k_projection','indexer','BF16',batch*entries,ci,hd,
            formula='2*B*(floor((P+T)/r)-floor(P/r))*c*ci')

    if not cache_only and mode in ('full','reindex') and (P+T)//ratio:
        active = T if phase=='prefill' else max(0,P+T-max(P,ratio-1))
        add('index.q_projection','indexer','FP8',batch*active,Hi*ci,q)
        add('index.head_weights','indexer','BF16',batch*active,Hi,d)
        if indexer=='reference':
            pairs=T*((P+T)//ratio) if phase=='prefill' else visible_pairs(P,T,ratio)
            dtype='BF16';formula='2*B*Hi*ci*(T*floor((P+T)/r) or U_r for decode)'
        else:
            pairs=(visible_pairs(P,T,ratio) if mode=='full' else
                   candidate_pairs(P,T,ratio,c.candidate_topk_blocks,c.candidate_block_size,candidate_policy))
            dtype='FP4';formula='2*B*Hi*ci*'+('U_r' if mode=='full' else 'candidate_pairs')
        rectangular = indexer=='reference' and phase=='prefill'
        add('index.full_qk' if mode=='full' else 'index.candidate_qk','indexer',dtype,Hi,(P+T)//ratio if rectangular else None,ci,batch*T,
            formula=formula,shape_kind='ragged_qk' if indexer=='native' or phase=='decode' else 'rectangular_index',
            operand='A4K4 (native)' if indexer=='native' else 'BF16 x BF16 (fake-quantized FP4 values)',
            pairs=pairs,heads=Hi)
    return rows


def _head(count, batch, phase, config):
    if not count:
        return []
    return [dict(phase=phase,segment='lm_head',layer_id=-1,mode='head',ratio=0,
        past_tokens=0,query_tokens=count,local_past=0,batch=batch,indexer='not_applicable',
        kernel='lm_head',component='lm_head',precision='FP32',flops=2*batch*count*config.dim*config.vocab_size,
        operand_format='FP32 x FP32; checkpoint weight BF16',accumulator_precision='FP32',
        precision_basis='released reference multiply dtype',m=batch*count,n=config.vocab_size,k=config.dim,
        repeat=1,shape_kind='dense',valid_pairs=None,formula='2*N_logits*d*V')]


def _stack(stack, past, count, local, phase, segment, config, **options):
    rows=[]
    use_engram=options.pop('include_engram',True)
    for layer in layer_schedule(config):
        if layer['stack']==stack:
            rows.extend(block_work(mode=layer['mode'],ratio=layer['ratio'],past_tokens=past,query_tokens=count,
                local_past=local,phase=phase,segment=segment,layer_id=layer['layer_id'],config=config,
                include_engram=use_engram and layer['engram'],**options))
    return rows


def simplified_prefill_work(input_tokens, *, batch=1, config=DEFAULT_CONFIG):
    """Encoder core + first decoder cache/replay; native Indexer, no peripherals.

    This is the approved prefill study scope. The remaining decoder layers are
    deliberately absent; use prefill_work for the separate full-CED audit.
    """
    _integer('input_tokens', input_tokens, 1)
    _integer('batch', batch, 1)
    if input_tokens > config.max_context:
        raise ValueError('Input exceeds configured context limit')
    S = input_tokens
    first = layer_schedule(config)[config.encoder_layers]
    if first['mode'] != 'full' or first['ratio'] != 1:
        raise ValueError('Simplified scope requires a Full r=1 first decoder layer')
    options = dict(batch=batch, config=config, indexer='native',
                   include_mhc=False, include_engram=False)
    rows = _stack('encoder', 0, S, 0, 'prefill', 'encoder_prefill', config,
                  batch=batch, indexer='native', include_mhc=False, include_engram=False)
    rows += block_work(mode='full', ratio=1, query_tokens=S, cache_only=True,
                       layer_id=first['layer_id'], segment='decoder_cache_build', **options)
    R = min(S, config.window_size)
    rows += block_work(mode='full', ratio=1, past_tokens=S-R, query_tokens=R,
                       local_past=0, build_global=False, layer_id=first['layer_id'],
                       segment='decoder_replay', **options)
    return rows


def prefill_work(input_tokens, *, batch=1, config=DEFAULT_CONFIG, prefill_schedule='ced',
                 indexer='native', candidate_policy='pinned_blocks', include_mhc=True,
                 include_engram=True, include_head=True):
    """Cold prompt, including first-token logits and (by default) CED replay."""
    _integer('input_tokens',input_tokens,1); _integer('batch',batch,1)
    if prefill_schedule not in ('ced','full'):
        raise ValueError('Unknown prefill schedule')
    S=input_tokens
    options=dict(batch=batch,indexer=indexer,candidate_policy=candidate_policy,include_mhc=include_mhc,
                 include_engram=include_engram)
    rows=_stack('encoder',0,S,0,'prefill','encoder_prefill',config,**options)
    if prefill_schedule=='full':
        rows+=_stack('decoder',0,S,0,'prefill','decoder_prefill',config,**options)
    else:
        for layer in layer_schedule(config):
            if layer['stack']=='decoder' and layer['mode']=='full':
                rows+=block_work(mode='full',ratio=layer['ratio'],query_tokens=S,batch=batch,
                    config=config,cache_only=True,layer_id=layer['layer_id'],segment='decoder_cache_build',
                    indexer=indexer,candidate_policy=candidate_policy)
        R=min(S,config.window_size)
        rows+=_stack('decoder',S-R,R,0,'prefill','decoder_replay',config,build_global=False,**options)
    return rows+(_head(1,batch,'prefill',config) if include_head else [])


def decode_work(input_tokens, steps, *, batch=1, config=DEFAULT_CONFIG, indexer='native',
                candidate_policy='pinned_blocks', include_mhc=True, include_engram=True, include_head=True):
    """Exactly `steps` one-token forwards, growing history after every step."""
    _integer('input_tokens',input_tokens,1); _integer('steps',steps); _integer('batch',batch,1)
    options=dict(batch=batch,indexer=indexer,candidate_policy=candidate_policy,include_mhc=include_mhc,
                 include_engram=include_engram)
    rows=[]
    for stack in ('encoder','decoder'):
        rows+=_stack(stack,input_tokens,steps,input_tokens,'decode','decode_'+stack,config,**options)
    return rows+(_head(steps,batch,'decode',config) if include_head else [])


def summarize(rows):
    totals=dict.fromkeys(PRECISIONS,0)
    for r in rows:
        totals[r['precision']]+=r['flops']
    return totals


def aggregate(rows, by=('phase','kernel','precision')):
    """Regroup work without losing integers. `by` can be a column or sequence."""
    by=(by,) if isinstance(by,str) else tuple(by)
    grouped=defaultdict(int)
    for r in rows:
        grouped[tuple(r[k] for k in by)]+=r['flops']
    return [dict(zip(by,key),flops=flops) for key,flops in grouped.items()]


def model_work(input_tokens, output_tokens=512, *, batch=1, config=DEFAULT_CONFIG,
               prefill_schedule='ced', indexer='native', candidate_policy='pinned_blocks',
               include_mhc=True, include_engram=True, include_head=True, strict_context=False):
    """One request; output token one comes from prefill, followed by O-1 steps."""
    _integer('input_tokens',input_tokens,1); _integer('output_tokens',output_tokens,1)
    _integer('batch',batch,1)
    extrapolated=input_tokens+output_tokens>config.max_context
    if strict_context and extrapolated:
        raise ValueError('Input plus output exceeds configured context limit')
    options=dict(batch=batch,config=config,indexer=indexer,candidate_policy=candidate_policy,
                 include_mhc=include_mhc,include_engram=include_engram,include_head=include_head)
    prefill=prefill_work(input_tokens,prefill_schedule=prefill_schedule,**options)
    decode=decode_work(input_tokens,output_tokens-1,**options)
    return dict(input_tokens=input_tokens,output_tokens=output_tokens,decode_steps=output_tokens-1,batch=batch,
        prefill_schedule=prefill_schedule,indexer=indexer,candidate_policy=candidate_policy,
        extrapolated=extrapolated,context_limit=config.max_context,source_revision=SOURCE_REVISION,
        prefill=prefill,decode=decode,
        totals=dict(prefill=summarize(prefill),decode=summarize(decode),full=summarize(prefill+decode)))
