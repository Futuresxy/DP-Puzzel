#include "detail.hpp"
#include <algorithm>

// S5 T2H4Q8E16 group and scale; S6 top alignment; S7 top tree; S8 pack.
// Token value = sign * magnitude * 2^(anchor_raw-(width-1)). Its raw
// fraction is retained for auditing, while anchor_raw already removes biases.

namespace dp {
// S5 two-input tree preserves S4 F and grows I by one.
// S2 unsigned scale pair.
// Precision / signal | S | I | F
// ------------------ | - | - | -
// A/B scale          | 0 | 1 | 3
// Scale pair         | 0 | 2 | 6
// S5 unsigned scale multiply. A=magnitude, B=scale pair, Y=product.
// Precision | A S | A I | A F | B S | B I | B F | Y S | Y I | Y F
// --------- | --- | --- | --- | --- | --- | --- | --- | --- | ---
// NVFP4     | 0   | 10  | 4   | 0   | 2   | 6   | 0   | 12  | 10
// HiF4      | 0   | 8   | 6   | 0   | 2   | 6   | 0   | 10  | 12
// Product low padding is group_mag_bits()-22; sign travels separately.
// P=c.local_fraction() (default 26). SM carries one separate sign bit.
// S5 group output (SM).
// Precision / signal | S | I  | F
// ------------------ | - | -- | ----
// TF32               | 1 | 3  | P+2
// FP16 / BF16        | 1 | 4  | P+1
// MXFP8 / MXFP6      | 1 | 5  | P
// MXFP4              | 1 | 10 | P-5
// NVFP4              | 1 | 12 | P-7
// HiF4               | 1 | 10 | P-5
// INT8               | 1 | 18 | P-13
// LZD reads the listed I/F as unsigned magnitude (S=0).
void stage_group(const Config& c,State& s,bool do_detect) {
  const auto t=s.request.a_type; const auto& f=format(t);
  Json scale_trace=Json::array();
  for(unsigned g=0;g<c.groups();++g) {
    const Big sop=tree_sum({s.lanes[g*lanes_per_group],s.lanes[g*lanes_per_group+1]},c.lane_bits());
    unsigned fraction=c.lane_fraction(t);
    Token out; out.width=c.group_mag_bits(); out.special=s.group_special[g];
    bool all_negative=true;
    for(unsigned i=g*lanes_per_group*f.lane_elements;i<(g+1)*lanes_per_group*f.lane_elements;++i)
      all_negative&=s.products[i].negative;
    out.negative=sop<0 || (sop==0 && all_negative);
    out.magnitude=abs_big(sop);
    check_unsigned(out.magnitude,out.width,"group SOP magnitude");
    const auto& sa=s.scale_a[g]; const auto& sb=s.scale_b[g];
    const Big factor=sa.magnitude*sb.magnitude;
    out.special.nan|=sa.category==Class::NaN || sb.category==Class::NaN;
    out.special.invalid|=sa.signaling || sb.signaling;
    if(factor==0 && (out.special.positive_inf || out.special.negative_inf)) {
      out.special.invalid=true; out.special.positive_inf=false; out.special.negative_inf=false;
    }
    if(t==DataType::NVFP4 || t==DataType::HIF4) {
      const unsigned magnitude_width=e_compact_group_bits-1;
      const unsigned coefficient_width=2*scale_magnitude_bits;
      const unsigned product_width=magnitude_width+coefficient_width;
      const unsigned structural=c.group_bits()-e_compact_group_bits;
      const unsigned pad=out.width-product_width;
      if((out.magnitude & mask(structural))!=0)
        throw std::logic_error("scale compact extraction lost nonzero bits");
      const Big compact=out.magnitude>>structural;
      check_unsigned(compact,magnitude_width,"compact SOP magnitude");
      check_unsigned(factor,coefficient_width,"scale coefficient");
      const Big product=compact*factor;
      check_unsigned(product,product_width,"unsigned scale product");
      if(s.tracing) scale_trace.push_back({{"sop_magnitude_bits",magnitude_width},{"coefficient_bits",coefficient_width},
        {"product_bits",product_width},{"sop_magnitude",compact.str()},
        {"coefficient",factor.str()},{"product",product.str()}});
      fraction=fraction-structural+2*scale_fraction_bits+pad;
      out.magnitude=product<<pad;
    }
    out.fraction=fraction;
    if(t!=DataType::INT8) {
      const int ebias=f.lane_elements==q_elements_per_lane?15:(f.lane_elements==e_elements_per_lane?0:static_cast<int>(f.bias));
      int alpha=s.r[g]-2*ebias;
      if(f.scale!=ScaleType::NONE) alpha+=sa.exponent+sb.exponent-2*static_cast<int>(scale_bias);
      out.anchor_raw=alpha-static_cast<int>(fraction)+static_cast<int>(out.width)-1;
    }
    s.groups.push_back(out);
  }
  finish_group_stage(s,do_detect,scale_trace);
}
} // namespace dp
