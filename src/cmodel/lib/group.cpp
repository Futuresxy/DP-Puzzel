#include "detail.hpp"
#include <algorithm>

// S5 T2H4Q8E16 group and scale; S6 top alignment; S7 top tree; S8 pack.
// Token value = sign * magnitude * 2^(anchor_raw-(width-1)). Its raw
// fraction is retained for auditing, while anchor_raw already removes biases.

namespace dp {
namespace {
void detect(Token& t) {
  if(t.active()) t.z=clz(t.magnitude,t.width);
  else { t.z=0; t.anchor_raw=0; }
}
}
// S5 two-input tree preserves S4 F and grows I by one. Scale pair multiplies
// S0I1F3 operands to S0I2F6; adding a zero sign gives TC S1I2F6.
// NVFP4/HiF4 compact TC S1I10F4/S1I8F6 -> native S1I13F10/S1I11F12,
// then use S1I12F10/S1I10F12 and append group_bits()-23 low zeros.
// SM output with P=local_fraction(): T S1I3F(P+2), H S1I4F(P+1),
// Q S1I5F(P), MXFP4 S1I10F(P-5), NVFP4 S1I12F(P-7), HiF4 S1I10F(P-5),
// INT8 S1I18F(P-13). LZD only reads the unsigned magnitude.
void stage_group(const Config& c,State& s,bool do_detect) {
  const auto t=s.request.a_type; const auto& f=format(t);
  Json scale_trace=Json::array();
  for(unsigned g=0;g<c.groups();++g) {
    Big sop=tree_sum({s.lanes[g*lanes_per_group],s.lanes[g*lanes_per_group+1]},c.lane_bits());
    unsigned fraction=c.lane_fraction(t);
    Token out; out.width=c.group_mag_bits(); out.special=s.group_special[g];
    bool all_negative=true;
    for(unsigned i=g*lanes_per_group*f.lane_elements;i<(g+1)*lanes_per_group*f.lane_elements;++i)
      all_negative&=s.products[i].negative;
    const bool pre_negative=sop<0 || (sop==0 && all_negative);
    const auto& sa=s.scale_a[g]; const auto& sb=s.scale_b[g];
    const Big factor=sa.magnitude*sb.magnitude;
    out.special.nan|=sa.category==Class::NaN || sb.category==Class::NaN;
    out.special.invalid|=sa.signaling || sb.signaling;
    if(factor==0 && (out.special.positive_inf || out.special.negative_inf)) {
      out.special.invalid=true; out.special.positive_inf=false; out.special.negative_inf=false;
    }
    if(t==DataType::NVFP4 || t==DataType::HIF4) {
      // One shared signed15 x positive-signed9 multiplication. Do not add
      // per-format operand compaction/muxes for NVFP4 versus HiF4.
      const unsigned sw=e_compact_group_bits;
      const unsigned fw=2*scale_magnitude_bits;
      const unsigned structural=c.group_bits()-sw;
      if((sop % (Big(1)<<structural))!=0)
        throw std::logic_error("scale compact extraction lost nonzero bits");
      Big compact=sop/(Big(1)<<structural), coeff=factor;
      check_signed(compact,sw,"compact SOP"); check_unsigned(coeff,fw,"compact scale");
      Big product=compact*coeff;
      check_signed(product,sw+fw+1,"full signed scale product");
      // The coefficient's sign bit is always zero: only a redundant high
      // sign-extension bit is removed, identically for both formats.
      check_signed(product,sw+fw,"scale product useful width");
      if(s.tracing) scale_trace.push_back({{"sop_signed_bits",sw},{"coefficient_signed_bits",fw+1},
        {"product_signed_bits",sw+fw+1},{"useful_signed_bits",sw+fw},
        {"sop",compact.str()},{"coefficient",coeff.str()},{"product",product.str()}});
      fraction=fraction-structural+2*scale_fraction_bits+c.group_bits()-(sw+fw);
      sop=product<<(c.group_bits()-(sw+fw));
    }
    check_signed(sop,c.group_bits(),"group SOP");
    out.negative=sop<0 || (sop==0 && pre_negative);
    out.magnitude=abs_big(sop); out.fraction=fraction;
    check_unsigned(out.magnitude,out.width,"group absolute value");
    if(t!=DataType::INT8) {
      const int ebias=f.lane_elements==q_elements_per_lane?15:(f.lane_elements==e_elements_per_lane?0:static_cast<int>(f.bias));
      int alpha=s.r[g]-2*ebias;
      if(f.scale!=ScaleType::NONE) alpha+=sa.exponent+sb.exponent-2*static_cast<int>(scale_bias);
      out.anchor_raw=alpha-static_cast<int>(fraction)+static_cast<int>(out.width)-1;
      if(do_detect) detect(out);
    }
    s.groups.push_back(out);
  }
  s.c=unpack_c(s.request.c_type,s.request.c);
  if(do_detect && s.request.c_type==CType::FP32) detect(s.c);
  if(s.tracing) {
    Json group=Json::array(); for(const auto& tkn:s.groups) group.push_back(token_json(tkn));
    trace(s,do_detect?"group_scale_abs_LZD_and_C":"group_scale_abs_and_C",{{"groups",group},{"c",token_json(s.c)},
      {"scale_multiplier",scale_trace}});
  }
}
void stage_detect(const Config&,State& s) {
  if(s.request.c_type==CType::FP32) {
    for(auto& t:s.groups) detect(t);
    detect(s.c);
  }
  if(s.tracing) {
    Json group=Json::array(); for(const auto& t:s.groups) group.push_back(token_json(t));
    trace(s,"extra_LZD_register",{{"groups",group},{"c",token_json(s.c)}});
  }
}
// S6: pad each floating source by global_mag_bits()-source.width low zeros.
// The unsigned shift yields S0I1F(global_mag_bits()-1) at E_max, then TC.
// INT8+INT32 leaves use TC S1I32F(global_mag_bits()-32).
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
// S7: add ceil(log2(K_FP16/4+1)) integer bits to each S6 leaf format.
void stage_total(const Config& c,State& s) {
  s.sum=tree_sum(s.aligned,c.global_signed_align_width); check_signed(s.sum,c.sum_bits(),"final sum");
  trace(s,"total_sop_tree",{{"sop_tc",s.sum.str()},{"width",c.sum_bits()},
    {"f",s.request.c_type==CType::INT32?c.global_mag_bits()-int32_bits:c.global_mag_bits()-1},{"E_max",s.common}});
}
// S8: FP32 coefficient S0I1F23 after normalization/RNE -> S1/E8/F23.
// INT8+INT32 drops structural zeros and wraps to TC S1I31F0.
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
