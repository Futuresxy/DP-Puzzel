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
void stage_pairs(const Config &config, State &state) {
  Json products = Json::array();
  Json pairs = Json::array();
  Json scales = Json::array();
  for (unsigned lane = 0; lane < config.lanes(); ++lane) {
    std::vector<Big> signed_products;
    std::vector<Big> lane_pairs;
    bool all_negative = true;
    for (unsigned pair_index = 0; pair_index < e_elements_per_lane; ++pair_index) {
      const unsigned element_index = lane * e_elements_per_lane + pair_index;
      const auto &operand_a = state.operands_a[element_index];
      const auto &operand_b = state.operands_b[element_index];
      check_unsigned(operand_a.magnitude, 4, "E A mantissa");
      check_unsigned(operand_b.magnitude, 4, "E B mantissa");
      const Big magnitude = operand_a.magnitude * operand_b.magnitude;
      check_unsigned(magnitude, 8, "E unsigned product");
      const bool negative = operand_a.negative != operand_b.negative;
      const Big value = signed_value(magnitude, negative);
      check_signed(value, 9, "E signed product");
      signed_products.push_back(value);
      all_negative &= negative; // Includes zero products, before pair cancellation.
      if (state.tracing)
        products.push_back({{"m", magnitude.str()},
                            {"sign", negative},
                            {"f", operand_a.fractional_bits + operand_b.fractional_bits}});
    }
    for (unsigned pair_index = 0; pair_index < e_elements_per_lane; pair_index += 2) {
      Big pair = signed_products[pair_index] + signed_products[pair_index + 1];
      check_signed(pair, e_pair_bits, "E S2 pair");
      lane_pairs.push_back(std::move(pair));
    }
    unsigned lane_left_shift = e_guard_bits; // MX/NV: static low padding F2 -> F4.
    if (state.request.a_type == DataType::HIF4)
      lane_left_shift =
          static_cast<unsigned>(state.operands_a[lane * e_elements_per_lane].exponent +
                                state.operands_b[lane * e_elements_per_lane].exponent);
    if (lane_left_shift > e_guard_bits)
      throw std::logic_error("E e2 left shift outside 0..2");
    if (state.tracing)
      pairs.push_back(bigs_json(lane_pairs));
    state.e_frontend.pairs.push_back(std::move(lane_pairs));
    state.e_frontend.lane_shift.push_back(lane_left_shift);
    state.e_frontend.all_negative.push_back(all_negative);
  }
  for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
    const Big coefficient =
        state.scale_a[group_index].magnitude * state.scale_b[group_index].magnitude;
    check_unsigned(coefficient, 2 * scale_magnitude_bits, "E scale coefficient");
    state.e_frontend.scale_coefficients.push_back(coefficient);
    state.e_frontend.scale_exponents.push_back(state.scale_a[group_index].exponent +
                                               state.scale_b[group_index].exponent);
    if (state.tracing)
      scales.push_back({{"coefficient", coefficient.str()},
                        {"exponent_sum", state.e_frontend.scale_exponents.back()}});
  }
  trace(state, "e_multiply_and_pairs",
        {{"products", products},
         {"pairs_tc", pairs},
         {"pair_width", e_pair_bits},
         {"lane_shift", state.e_frontend.lane_shift},
         {"all_negative", state.e_frontend.all_negative},
         {"scale_pairs", scales}});
}

void stage_lane_sum(const Config &config, State &state) {
  for (unsigned lane = 0; lane < config.lanes(); ++lane) {
    Big value = tree_sum(state.e_frontend.pairs[lane], e_pair_bits);
    check_signed(value, e_lane_raw_bits, "E S3 lane SOP");
    state.lanes.push_back(std::move(value));
  }
  trace(state, "e_lane_sop_tree",
        {{"sop_tc", bigs_json(state.lanes)},
         {"width", e_lane_raw_bits},
         {"f", state.request.a_type == DataType::HIF4 ? 4 : 2}});
}
} // namespace dp::e_frontend
