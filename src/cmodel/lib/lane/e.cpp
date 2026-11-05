#include "detail.hpp"
#include <stdexcept>

// E8 frontend, S2 multiplier/pair registers and S3 lane tree.
// S1 reuses unpack_element/unpack_scale; e1 is already in the magnitude.
// Raw multiplier sign is separate. TC widths include S; I excludes S.
// Precision     | Product S | I | F | Pair S | I | F | Lane S | I | F
// ------------- | --------- | - | - | ------ | - | - | ------ | - | -
// MXFP4 / NVFP4 | 0         | 6 | 2 | 1      | 7 | 2 | 1      | 9 | 2
// HiF4          | 0         | 4 | 4 | 1      | 5 | 4 | 1      | 7 | 4
namespace dp::e_frontend {
void stage_pairs(const Config& c,State& s) {
  Json products=Json::array(),pairs=Json::array(),scales=Json::array();
  for(unsigned lane=0;lane<c.lanes();++lane) {
    std::vector<Big> signed_products, lane_pairs;
    bool all_negative=true;
    for(unsigned j=0;j<e_elements_per_lane;++j) {
      const unsigned i=lane*e_elements_per_lane+j;
      const auto& a=s.a[i]; const auto& b=s.b[i];
      check_unsigned(a.magnitude,4,"E A mantissa");
      check_unsigned(b.magnitude,4,"E B mantissa");
      const Big magnitude=a.magnitude*b.magnitude;
      check_unsigned(magnitude,8,"E unsigned product");
      const bool negative=a.negative!=b.negative;
      const Big value=signed_value(magnitude,negative);
      check_signed(value,9,"E signed product");
      signed_products.push_back(value);
      all_negative&=negative; // Includes zero products, before pair cancellation.
      if(s.tracing) products.push_back({{"m",magnitude.str()},{"sign",negative},
        {"f",a.fraction+b.fraction}});
    }
    for(unsigned j=0;j<e_elements_per_lane;j+=2) {
      Big pair=signed_products[j]+signed_products[j+1];
      check_signed(pair,e_pair_bits,"E S2 pair");
      lane_pairs.push_back(std::move(pair));
    }
    unsigned shift=e_guard_bits; // MX/NV: static low padding F2 -> F4.
    if(s.request.a_type==DataType::HIF4)
      shift=static_cast<unsigned>(s.a[lane*e_elements_per_lane].exponent+
                                  s.b[lane*e_elements_per_lane].exponent);
    if(shift>e_guard_bits) throw std::logic_error("E e2 left shift outside 0..2");
    if(s.tracing) pairs.push_back(bigs_json(lane_pairs));
    s.e.pairs.push_back(std::move(lane_pairs));
    s.e.lane_shift.push_back(shift);
    s.e.all_negative.push_back(all_negative);
  }
  for(unsigned g=0;g<c.groups();++g) {
    const Big coefficient=s.scale_a[g].magnitude*s.scale_b[g].magnitude;
    check_unsigned(coefficient,2*scale_magnitude_bits,"E scale coefficient");
    s.e.scale_coefficients.push_back(coefficient);
    s.e.scale_exponents.push_back(s.scale_a[g].exponent+s.scale_b[g].exponent);
    if(s.tracing) scales.push_back({{"coefficient",coefficient.str()},
      {"exponent_sum",s.e.scale_exponents.back()}});
  }
  trace(s,"e_multiply_and_pairs",{{"products",products},{"pairs_tc",pairs},
    {"pair_width",e_pair_bits},{"lane_shift",s.e.lane_shift},
    {"all_negative",s.e.all_negative},{"scale_pairs",scales}});
}

void stage_lane_sum(const Config& c,State& s) {
  for(unsigned lane=0;lane<c.lanes();++lane) {
    Big value=tree_sum(s.e.pairs[lane],e_pair_bits);
    check_signed(value,e_lane_raw_bits,"E S3 lane SOP");
    s.lanes.push_back(std::move(value));
  }
  trace(s,"e_lane_sop_tree",{{"sop_tc",bigs_json(s.lanes)},{"width",e_lane_raw_bits},
    {"f",s.request.a_type==DataType::HIF4?4:2}});
}
} // namespace dp::e_frontend
