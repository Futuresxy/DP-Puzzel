#include "detail.hpp"
#include <algorithm>

// T1H2Q4E8: S2 product/group-MAX, S3 unsigned RTZ (E pairs exact),
// S4 balanced lane sum. All shifts act on magnitude before restoring sign.

namespace dp {
namespace {
// S2 S0 operands/products: TF32/FP16 I1F10 -> I2F20, BF16 I1F7 -> I2F14,
// MXFP8/6 I1F3 -> I2F6, MXFP4/NVFP4 I3F1 -> I6F2, HiF4 I2F2 -> I4F4,
// INT8 I8F0 -> I16F0. Sign is carried separately.
Big multiply(DataType t,const Big& a,const Big& b,unsigned in_lane) {
  if(t==DataType::TF32 || t==DataType::FP16) {
    const Big ah=a>>mul_lo_bits,al=a&mask(mul_lo_bits),bh=b>>mul_lo_bits,bl=b&mask(mul_lo_bits);
    return (ah*bh<<(2*mul_lo_bits))+((ah*bl+al*bh)<<mul_lo_bits)+al*bl;
  }
  if(t==DataType::INT8 && in_lane%2) {
    return a*(b&mask(mul_lo_bits))+((a*(b>>mul_lo_bits))<<mul_lo_bits);
  }
  return a*b;
}
}
void stage_products(const Config& c,State& s) {
  const auto t=s.request.a_type; const auto n=format(t).lane_elements;
  s.r.assign(c.groups(),0); s.group_special.resize(c.groups());
  std::vector<bool> active(c.groups(),false);
  Json pjson=Json::array(),sf=Json::array();
  for(unsigned i=0;i<s.a.size();++i) {
    const auto& a=s.a[i]; const auto& b=s.b[i]; Product p;
    p.negative=a.negative!=b.negative; p.exponent=a.exponent+b.exponent;
    p.fraction=a.fraction+b.fraction; p.special=product_special(a,b);
    p.magnitude=multiply(t,a.magnitude,b.magnitude,i%n);
    const unsigned g=i/(lanes_per_group*n);
    s.group_special[g].merge(p.special);
    if(p.magnitude!=0 && !p.special.active()) {
      s.r[g]=active[g]?std::max(s.r[g],p.exponent):p.exponent; active[g]=true;
    }
    s.products.push_back(p);
    if(s.tracing) pjson.push_back({{"m",p.magnitude.str()},{"sign",p.negative},{"exp",p.exponent},{"f",p.fraction},{"special",special_json(p.special)}});
  }
  if(s.tracing) {
    for(unsigned g=0;g<c.groups();++g) sf.push_back({{"coefficient",Big(s.scale_a[g].magnitude*s.scale_b[g].magnitude).str()},
      {"exponent_sum",s.scale_a[g].exponent+s.scale_b[g].exponent}});
    trace(s,"multiply_and_group_max",{{"products",pjson},{"r",s.r},{"scale_pairs",sf}});
  }
}
// P=local_fraction(). S3 shift magnitudes become TC leaves of the same I/F.
// T/H/Q S1I2F(P), MXFP4/NVFP4 S1I7F(P-5), HiF4 S1I5F(P-3),
// INT8 S1I15F(P-13). E signed pairs before padding are I7F2 or I5F4.
void stage_local_align(const Config& c,State& s) {
  const auto t=s.request.a_type; const unsigned n=format(t).lane_elements;
  Json deltas=Json::array();
  for(unsigned lane=0;lane<c.lanes();++lane) {
    std::vector<Big> leaf; Json ld=Json::array(); const unsigned base=lane*n,g=lane/lanes_per_group;
    if(n==e_elements_per_lane) {
      const unsigned pad=c.leaf_bits()-(e_pair_bits+e_guard_bits);
      for(unsigned j=0;j<n;j+=2) {
        const auto& p=s.products[base+j]; const auto& q=s.products[base+j+1];
        Big pair=signed_value(p.magnitude,p.negative)+signed_value(q.magnitude,q.negative);
        check_signed(pair,e_pair_bits,"E pair");
        int delta=t==DataType::HIF4 && pair!=0?s.r[g]-p.exponent:0;
        if(delta<0 || delta>static_cast<int>(e_guard_bits)) throw std::logic_error("HiF e2 delta outside guard range");
        bool lost=false; Big mag=rtz(abs_big(pair)<<e_guard_bits,delta,lost);
        if(lost) throw std::logic_error("HiF guarded pair lost precision");
        leaf.push_back(signed_value(mag,pair<0)<<pad); ld.push_back(delta);
      }
    } else {
      for(unsigned j=0;j<n;++j) {
        const auto& p=s.products[base+j]; Big v=0; int delta=0;
        if(t==DataType::INT8) v=signed_value(p.magnitude,p.negative)<<(c.leaf_bits()-int_product_bits);
        else if(p.magnitude!=0 && !p.special.active()) {
          delta=s.r[g]-p.exponent;
          if(delta<0) throw std::logic_error("negative local delta");
          const Big m=p.magnitude<<(c.local_fraction()-p.fraction);
          check_unsigned(m,c.local_shift_mag_width,"local shift input");
          Big y=rtz(m,delta,s.result.flags.local_truncated);
          v=signed_value(y,p.negative);
        }
        check_signed(v,c.leaf_bits(),"local leaf"); leaf.push_back(v); ld.push_back(delta);
      }
    }
    s.leaves.push_back(std::move(leaf)); deltas.push_back(ld);
  }
  if(s.tracing) {
    Json leaves=Json::array(); for(const auto& l:s.leaves) leaves.push_back(bigs_json(l));
    trace(s,"local_align_and_E_pairs",{{"leaves_tc",leaves},{"delta",deltas},{"width",c.leaf_bits()}});
  }
}
// S4 TC: T S1I2F(P+2), H S1I3F(P+1), Q S1I4F(P), MXFP4/NVFP4
// S1I9F(P-5), HiF4 S1I7F(P-3), INT8 S1I17F(P-13).
void stage_lane_sum(const Config& c,State& s) {
  const auto t=s.request.a_type;
  for(const auto& l:s.leaves) {
    Big sum=tree_sum(l,c.leaf_bits());
    const unsigned pad=ceil_log2(q_elements_per_lane)-ceil_log2(static_cast<unsigned>(l.size()));
    sum<<=pad; check_signed(sum,c.lane_bits(),"lane SOP"); s.lanes.push_back(sum);
  }
  trace(s,"lane_sop_tree",{{"sop_tc",bigs_json(s.lanes)},{"width",c.lane_bits()},{"f",c.lane_fraction(t)}});
}
} // namespace dp
