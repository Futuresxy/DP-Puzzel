#include "detail.hpp"
#include <algorithm>

// T1H2Q4E8: S2 product/group-MAX, S3 unsigned RTZ (E pairs exact),
// v1.8: E bypasses RTZ/abs, uses signed narrow pairs and fuses local e2 after S4 tree.
// Other frontends keep the v1.7 magnitude-align contract.

namespace dp {
namespace {
// S2 unsigned mantissa operands A/B -> product Y. Sign is separate.
// Precision     | A/B S | A/B I | A/B F | Y S | Y I | Y F
// ------------- | ----- | ----- | ----- | --- | --- | ---
// TF32 / FP16   | 0     | 1     | 10    | 0   | 2   | 20
// BF16          | 0     | 1     | 7     | 0   | 2   | 14
// MXFP8 / MXFP6 | 0     | 1     | 3     | 0   | 2   | 6
// MXFP4 / NVFP4 | 0     | 3     | 1     | 0   | 6   | 2
// HiF4          | 0     | 2     | 2     | 0   | 4   | 4
// INT8          | 0     | 8     | 0     | 0   | 16  | 0
Big multiply(DataType datatype, const Big &operand_a, const Big &operand_b,
             unsigned lane_element_index) {
  if (datatype == DataType::TF32 || datatype == DataType::FP16) {
    const Big a_high = operand_a >> mul_lo_bits, a_low = operand_a & mask(mul_lo_bits),
              b_high = operand_b >> mul_lo_bits, b_low = operand_b & mask(mul_lo_bits);
    return (a_high * b_high << (2 * mul_lo_bits)) +
           ((a_high * b_low + a_low * b_high) << mul_lo_bits) + a_low * b_low;
  }
  if (datatype == DataType::INT8 && lane_element_index % 2) {
    return operand_a * (operand_b & mask(mul_lo_bits)) +
           ((operand_a * (operand_b >> mul_lo_bits)) << mul_lo_bits);
  }
  return operand_a * operand_b;
}
} // namespace
void stage_products(const Config &config, State &state) {
  const auto datatype = state.request.a_type;
  const auto element_count = format(datatype).lane_elements;
  state.group_max_exponents.assign(config.groups(), 0);
  state.group_special.resize(config.groups());
  std::vector<bool> active(config.groups(), false);
  Json products_json = Json::array();
  Json scale_pairs_json = Json::array();
  for (unsigned element_index = 0; element_index < state.operands_a.size(); ++element_index) {
    const auto &operand_a = state.operands_a[element_index];
    const auto &operand_b = state.operands_b[element_index];
    Product product;
    product.negative = operand_a.negative != operand_b.negative;
    product.exponent = operand_a.exponent + operand_b.exponent;
    product.fractional_bits = operand_a.fractional_bits + operand_b.fractional_bits;
    product.special = product_special(operand_a, operand_b);
    product.magnitude =
        multiply(datatype, operand_a.magnitude, operand_b.magnitude, element_index % element_count);
    const unsigned group_index = element_index / (lanes_per_group * element_count);
    state.group_special[group_index].merge(product.special);
    if (product.magnitude != 0 && !product.special.active() &&
        !(config.baseline_v18() && element_count == e_elements_per_lane)) {
      state.group_max_exponents[group_index] =
          active[group_index] ? std::max(state.group_max_exponents[group_index], product.exponent)
                              : product.exponent;
      active[group_index] = true;
    }
    state.products.push_back(product);
    if (state.tracing)
      products_json.push_back({{"m", product.magnitude.str()},
                               {"sign", product.negative},
                               {"exp", product.exponent},
                               {"f", product.fractional_bits},
                               {"special", special_json(product.special)}});
  }
  if (state.tracing) {
    for (unsigned group_index = 0; group_index < config.groups(); ++group_index)
      scale_pairs_json.push_back(
          {{"coefficient",
            Big(state.scale_a[group_index].magnitude * state.scale_b[group_index].magnitude).str()},
           {"exponent_sum",
            state.scale_a[group_index].exponent + state.scale_b[group_index].exponent}});
    trace(state, "multiply_and_group_max",
          {{"products", products_json},
           {"r", state.group_max_exponents},
           {"scale_pairs", scale_pairs_json}});
  }
}
// P=c.local_fraction() (default 26). I excludes S.
// S3 shift magnitude -> TC tree leaf. Both use the listed I/F.
// Precision                    | Shift S | Leaf S | I  | F
// ---------------------------- | ------- | ------ | -- | ----
// TF32 / FP16 / BF16 / MXFP8/6 | 0       | 1      | 2  | P
// MXFP4 / NVFP4                | 0       | 1      | 7  | P-5
// HiF4 (legacy)                | 0       | 1      | 5  | P-3
// v1.8 E pair slots: MX/NV S1I9F(P-7), HiF4 S1I7F(P-5); signed directly.
// INT8                         | 0       | 1      | 15 | P-13
// S3 E pair before guard/padding (TC, W10).
// Precision / signal | S | I | F
// ------------------ | - | - | -
// MXFP4 / NVFP4      | 1 | 7 | 2
// HiF4               | 1 | 5 | 4
void stage_local_align(const Config &config, State &state) {
  const auto datatype = state.request.a_type;
  const unsigned element_count = format(datatype).lane_elements;
  // S3 computes the physical MSB coordinate independently of the mantissa sum.
  if (config.baseline_v18()) {
    const int element_bias = element_count == q_elements_per_lane ? 15 :
                            element_count == e_elements_per_lane ? 0 : format(datatype).bias;
    unsigned group_fraction = config.lane_fraction(datatype);
    if (datatype == DataType::NVFP4 || datatype == DataType::HIF4)
      group_fraction -= 2; // compact14 * coefficient8 -> product22, pad to group slot.
    for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
      const int scale_exponent = format(datatype).scale == ScaleType::NONE ? 0 :
          state.scale_a[group_index].exponent + state.scale_b[group_index].exponent;
      state.group_raw_anchors.push_back(datatype == DataType::INT8 ? 0 :
          state.group_max_exponents[group_index] + scale_exponent - 2 * element_bias -
          static_cast<int>(group_fraction) + static_cast<int>(config.group_mag_bits()) - 1);
    }
  }
  Json deltas = Json::array();
  for (unsigned lane = 0; lane < config.lanes(); ++lane) {
    std::vector<Big> leaf;
    Json lane_deltas = Json::array();
    const unsigned base = lane * element_count;
    const unsigned group_index = lane / lanes_per_group;
    if (element_count == e_elements_per_lane) {
      const unsigned pad = config.leaf_bits() - (e_pair_bits + e_guard_bits);
      for (unsigned pair_index = 0; pair_index < element_count; pair_index += 2) {
        const auto &product = state.products[base + pair_index];
        const auto &next_product = state.products[base + pair_index + 1];
        Big pair = signed_value(product.magnitude, product.negative) +
                   signed_value(next_product.magnitude, next_product.negative);
        check_signed(pair, e_pair_bits, "E pair");
        if (config.baseline_v18()) {
          // Signed pair goes directly to the shared tree; reserve two bits for S4 e2.
          leaf.push_back(pair << pad);
          lane_deltas.push_back(0);
          continue;
        }
        int delta = datatype == DataType::HIF4 && pair != 0
                        ? state.group_max_exponents[group_index] - product.exponent
                        : 0;
        if (delta < 0 || delta > static_cast<int>(e_guard_bits))
          throw std::logic_error("HiF e2 delta outside guard range");
        bool lost = false;
        Big magnitude = rtz(abs_big(pair) << e_guard_bits, delta, lost);
        if (lost)
          throw std::logic_error("HiF guarded pair lost precision");
        leaf.push_back(signed_value(magnitude, pair < 0) << pad);
        lane_deltas.push_back(delta);
      }
    } else {
      for (unsigned pair_index = 0; pair_index < element_count; ++pair_index) {
        const auto &product = state.products[base + pair_index];
        Big aligned_value = 0;
        int delta = 0;
        if (datatype == DataType::INT8)
          aligned_value = signed_value(product.magnitude, product.negative)
                          << (config.leaf_bits() - int_product_bits);
        else if (product.magnitude != 0 && !product.special.active()) {
          delta = state.group_max_exponents[group_index] - product.exponent;
          if (delta < 0)
            throw std::logic_error("negative local delta");
          const Big magnitude = product.magnitude
                                << (config.local_fraction() - product.fractional_bits);
          check_unsigned(magnitude, config.local_shift_mag_width, "local shift input");
          Big shifted_magnitude = rtz(magnitude, delta, state.result.flags.local_truncated);
          aligned_value = signed_value(shifted_magnitude, product.negative);
        }
        check_signed(aligned_value, config.leaf_bits(), "local leaf");
        leaf.push_back(aligned_value);
        lane_deltas.push_back(delta);
      }
    }
    state.leaves.push_back(std::move(leaf));
    deltas.push_back(lane_deltas);
  }
  if (state.tracing) {
    Json leaves = Json::array();
    for (const auto &lane_leaves : state.leaves)
      leaves.push_back(bigs_json(lane_leaves));
    trace(state, "local_align_and_E_pairs",
          {{"leaves_tc", leaves}, {"delta", deltas}, {"width", config.leaf_bits()}});
  }
}
// P=c.local_fraction() (default 26).
// S4 lane SOP (TC).
// Precision / signal | S | I  | F
// ------------------ | - | -- | ----
// TF32               | 1 | 2  | P+2
// FP16 / BF16        | 1 | 3  | P+1
// MXFP8 / MXFP6      | 1 | 4  | P
// MXFP4 / NVFP4      | 1 | 9  | P-5
// HiF4 (legacy)      | 1 | 7  | P-3
// HiF4 (v1.8 fused)  | 1 | 9  | P-5
// INT8               | 1 | 17 | P-13
void stage_lane_sum(const Config &config, State &state) {
  const auto datatype = state.request.a_type;
  for (const auto &lane_leaves : state.leaves) {
    Big sum = tree_sum(lane_leaves, config.leaf_bits());
    const unsigned pad =
        ceil_log2(q_elements_per_lane) - ceil_log2(static_cast<unsigned>(lane_leaves.size()));
    sum <<= pad;
    if (config.baseline_v18() && format(datatype).lane_elements == e_elements_per_lane) {
      const unsigned lane_index = state.lanes.size();
      const unsigned shift = datatype == DataType::HIF4
          ? state.products[lane_index * e_elements_per_lane].exponent : e_guard_bits;
      // Exact left shift in the full lane slot; no RTZ and no cross-lane exponent.
      sum <<= shift;
    }
    check_signed(sum, config.lane_bits(), "lane SOP");
    state.lanes.push_back(sum);
  }
  trace(state, "lane_sop_tree",
        {{"sop_tc", bigs_json(state.lanes)},
         {"width", config.lane_bits()},
         {"f", config.lane_fraction(datatype)}});
}
} // namespace dp
