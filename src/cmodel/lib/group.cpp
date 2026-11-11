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
// HiF4 v1.8 | 0   | 10  | 4   | 0   | 2   | 6   | 0   | 12  | 10
// HiF4 legacy keeps I8F6 -> I10F12.
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
// HiF4 v1.8          | 1 | 12 | P-7
// HiF4 legacy        | 1 | 10 | P-5
// INT8               | 1 | 18 | P-13
// LZD reads the listed I/F as unsigned magnitude (S=0).
void stage_group(const Config &config, State &state, bool do_detect) {
  const auto datatype = state.request.a_type;
  const auto &format_info = format(datatype);
  Json scale_trace = Json::array();
  for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
    const Big sop = tree_sum({state.lanes[group_index * lanes_per_group],
                              state.lanes[group_index * lanes_per_group + 1]},
                             config.lane_bits());
    unsigned fraction = config.lane_fraction(datatype);
    Token out;
    out.width = config.group_mag_bits();
    out.special = state.group_special[group_index];
    bool all_negative = true;
    for (unsigned element_index = group_index * lanes_per_group * format_info.lane_elements;
         element_index < (group_index + 1) * lanes_per_group * format_info.lane_elements;
         ++element_index)
      all_negative &= state.products[element_index].negative;
    out.negative = sop < 0 || (sop == 0 && all_negative);
    out.magnitude = abs_big(sop);
    check_unsigned(out.magnitude, out.width, "group SOP magnitude");
    const auto &scale_a = state.scale_a[group_index];
    const auto &scale_b = state.scale_b[group_index];
    const Big factor = scale_a.magnitude * scale_b.magnitude;
    out.special.nan |= scale_a.category == Class::NaN || scale_b.category == Class::NaN;
    out.special.invalid |= scale_a.signaling || scale_b.signaling;
    if (factor == 0 && (out.special.positive_inf || out.special.negative_inf)) {
      out.special.invalid = true;
      out.special.positive_inf = false;
      out.special.negative_inf = false;
    }
    if (datatype == DataType::NVFP4 || datatype == DataType::HIF4) {
      const unsigned magnitude_width = e_compact_group_bits - 1;
      const unsigned coefficient_width = 2 * scale_magnitude_bits;
      const unsigned product_width = magnitude_width + coefficient_width;
      const unsigned structural = config.group_bits() - e_compact_group_bits;
      const unsigned pad = out.width - product_width;
      if ((out.magnitude & mask(structural)) != 0)
        throw std::logic_error("scale compact extraction lost nonzero bits");
      const Big compact = out.magnitude >> structural;
      check_unsigned(compact, magnitude_width, "compact SOP magnitude");
      check_unsigned(factor, coefficient_width, "scale coefficient");
      const Big product = compact * factor;
      check_unsigned(product, product_width, "unsigned scale product");
      if (state.tracing)
        scale_trace.push_back({{"sop_magnitude_bits", magnitude_width},
                               {"coefficient_bits", coefficient_width},
                               {"product_bits", product_width},
                               {"sop_magnitude", compact.str()},
                               {"coefficient", factor.str()},
                               {"product", product.str()}});
      fraction = fraction - structural + 2 * scale_fraction_bits + pad;
      out.magnitude = product << pad;
    }
    out.fractional_bits = fraction;
    if (datatype != DataType::INT8) {
      const int element_exponent_bias = format_info.lane_elements == q_elements_per_lane
                                            ? 15
                                            : (format_info.lane_elements == e_elements_per_lane
                                                   ? 0
                                                   : static_cast<int>(format_info.bias));
      int alpha = state.group_max_exponents[group_index] - 2 * element_exponent_bias;
      if (format_info.scale != ScaleType::NONE)
        alpha += scale_a.exponent + scale_b.exponent -
                 (config.baseline_v18() ? 0 : 2 * static_cast<int>(scale_bias));
      out.anchor_raw = alpha - static_cast<int>(fraction) + static_cast<int>(out.width) - 1;
    }
    if (config.baseline_v18() && out.anchor_raw != state.group_raw_anchors[group_index])
      throw std::logic_error("S3 precomputed anchor disagrees with S5 format");
    state.groups.push_back(out);
  }
  finish_group_stage(state, do_detect, scale_trace);
}
} // namespace dp
