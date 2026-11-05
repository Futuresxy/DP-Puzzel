#include "detail.hpp"
#include <algorithm>

// Shared S5 token completion/C decode and S6-S8. Both frontends call these
// exact stage functions; the source coordinate is always carried in Token.
namespace dp {
void detect_token(Token& t) {
  if(t.active()) t.z=clz(t.magnitude,t.width);
  else { t.z=0; t.anchor_raw=0; }
}
void finish_group_stage(State& s,bool do_detect,const Json& scale_trace) {
  if(do_detect && s.request.c_type==CType::FP32)
    for(auto& group:s.groups) detect_token(group);
  s.c=unpack_c(s.request.c_type,s.request.c);
  if(do_detect && s.request.c_type==CType::FP32) detect_token(s.c);
  if(s.tracing) {
    Json group=Json::array(); for(const auto& token:s.groups) group.push_back(token_json(token));
    trace(s,do_detect?"group_abs_scale_LZD_and_C":"group_abs_scale_and_C",
      {{"groups",group},{"c",token_json(s.c)},{"scale_multiplier",scale_trace}});
  }
}
void stage_detect(const Config&,State& s) {
  if(s.request.c_type==CType::FP32) {
    for(auto& t:s.groups) detect_token(t);
    detect_token(s.c);
  }
  if(s.tracing) {
    Json group=Json::array(); for(const auto& t:s.groups) group.push_back(token_json(t));
    trace(s,"extra_LZD_register",{{"groups",group},{"c",token_json(s.c)}});
  }
}
// S6 pad=global_mag_bits()-source.width. Let M=global_mag_bits().
// Unsigned aligned magnitude -> TC leaf. Both use the listed I/F.
// Precision          | Mag S | Leaf S | I  | F
// ------------------ | ----- | ------ | -- | ----
// All floating modes | 0     | 1      | 1  | M-1
// INT8 + INT32       | 0     | 1      | 32 | M-32
// Floating coordinates use E_max. Integers use structural low zeros.
void stage_global_align(const Config& c,State& s) {
  std::vector<Token> sources=s.groups; sources.push_back(s.c);
  const bool integer=s.request.c_type==CType::INT32;
  bool any=false; s.common=0;
  if(!integer) for(const auto& t:sources) if(t.active()) {
    const int e=t.anchor_raw-static_cast<int>(t.z);
    s.common=any?std::max(s.common,e):e; any=true;
  }
  Json controls=Json::array(); s.negative_zero=true;
  for(const auto& t:sources) {
    Big mag=0; int delta=0,net=0;
    if(integer) {
      if(t.magnitude%(Big(1)<<t.fraction)!=0) throw std::logic_error("integer lost structural bits");
      mag=(t.magnitude>>t.fraction)<<(c.global_mag_bits()-int32_bits);
    } else if(t.active()) {
      delta=s.common-(t.anchor_raw-static_cast<int>(t.z));
      net=t.anchor_raw-s.common;
      if(delta<0 || net!=static_cast<int>(t.z)-delta || net>static_cast<int>(t.z))
        throw std::logic_error("invalid fused shift relation");
      Big x=t.magnitude<<(c.global_mag_bits()-t.width);
      if(net>=0) mag=x<<net;
      else mag=rtz(x,-net,s.result.flags.global_truncated);
    }
    check_unsigned(mag,c.global_mag_bits(),"global shift output");
    s.aligned.push_back(signed_value(mag,t.negative));
    s.negative_zero&=(mag==0 && t.negative);
    controls.push_back({{"d",delta},{"net",net},{"z",t.z}});
  }
  trace(s,"global_max_and_bidirectional_align",{{"E_max",s.common},{"controls",controls},
    {"aligned_tc",bigs_json(s.aligned)},{"width",c.global_signed_align_width},
    {"f",integer?c.global_mag_bits()-int32_bits:c.global_mag_bits()-1}});
}
// K=c.k_fp16, G=K/4, L=ceil(log2(G+1)), W=c.global_signed_align_width.
// S7 total SOP (TC).
// Precision / signal | S | I    | F
// ------------------ | - | ---- | ----
// All floating modes | 1 | 1+L  | W-2
// INT8 + INT32       | 1 | 32+L | W-33
void stage_total(const Config& c,State& s) {
  s.sum=tree_sum(s.aligned,c.global_signed_align_width); check_signed(s.sum,c.sum_bits(),"final sum");
  trace(s,"total_sop_tree",{{"sop_tc",s.sum.str()},{"width",c.sum_bits()},
    {"f",s.request.c_type==CType::INT32?c.global_mag_bits()-int32_bits:c.global_mag_bits()-1},{"E_max",s.common}});
}
// S8 result formats.
// Precision / signal | S | I  | F
// ------------------ | - | -- | --
// FP32 coefficient   | 0 | 1  | 23
// INT32 output (TC)  | 1 | 31 | 0
// The final FP32 output encodes sign/exponent/fraction with widths 1/8/23.
void stage_output(const Config& c,State& s) {
  auto& r=s.result; r.id=s.request.id; r.type=s.request.c_type; r.last=s.request.last;
  if(r.type==CType::INT32) {
    Big value=s.sum/(Big(1)<<(c.global_mag_bits()-int32_bits));
    r.flags.integer_overflow=value<-(Big(1)<<(int32_bits-1)) || value>=(Big(1)<<(int32_bits-1));
    Big residue=value%(Big(1)<<int32_bits); if(residue<0) residue+=Big(1)<<int32_bits;
    r.bits=residue.convert_to<std::uint32_t>();
  } else {
    Special all=s.c.special; for(const auto& g:s.groups) all.merge(g.special);
    r.flags.invalid=all.invalid;
    if(all.nan || all.invalid) r.bits=canonical_nan;
    else if(all.positive_inf || all.negative_inf) r.bits=all.negative_inf?0xff800000u:0x7f800000u;
    else r.bits=round_fp32(s.sum,s.common-static_cast<int>(c.global_mag_bits()-1),s.negative_zero,r.flags);
  }
  trace(s,"output",{{"bits",r.bits},{"type",static_cast<unsigned>(r.type)},{"last",r.last}});
}
} // namespace dp
