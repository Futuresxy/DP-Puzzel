#include "detail.hpp"

// E16 frontend, S4 group sum/sign-magnitude and S5 scale/token registers.
// I excludes S. S4 is TC -> SM; all shifts are exact with checked growth.
// Precision     | S4 S | I  | F | Scale A S | I  | F | Scale Y S | I  | F
// ------------- | ---- | -- | - | --------- | -- | - | --------- | -- | --
// MXFP4         | 1    | 10 | 4 | 0         | 10 | 4 | bypass    | 10 | 4
// NVFP4 / HiF4  | 1    | 10 | 4 | 0         | 10 | 4 | 0         | 12 | 10
// Scale B is unsigned S0I2F6. Sign stays separate through S5/S6.
// M=c.group_mag_bits(). Group output (SM):
// Precision     | S | I  | F
// ------------- | - | -- | ----
// MXFP4         | 1 | 10 | M-10
// NVFP4 / HiF4  | 1 | 12 | M-12
namespace dp::e_frontend {
void stage_group_sum(const Config &config, State &state) {
  Json fused = Json::array();
  Json sops = Json::array();
  for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
    std::vector<Big> lanes;
    bool all_negative = true;
    for (unsigned lane_index = 0; lane_index < lanes_per_group; ++lane_index) {
      const unsigned lane = group_index * lanes_per_group + lane_index;
      Big value = state.lanes[lane];
      if (!config.architecture_v19) value <<= state.e_frontend.lane_shift[lane];
      check_signed(value, e_lane_fused_bits, "E S4 fused lane SOP");
      lanes.push_back(std::move(value));
      all_negative = all_negative && state.e_frontend.all_negative[lane];
    }
    const Big sop = tree_sum(lanes, e_lane_fused_bits);
    check_signed(sop, e_compact_group_bits, "E S4 group SOP");
    const Big magnitude = abs_big(sop);
    check_unsigned(magnitude, e_compact_group_bits - 1, "E S4 group magnitude");
    state.e_frontend.group_magnitudes.push_back(magnitude);
    state.e_frontend.group_negative.push_back(sop < 0 || (sop == 0 && all_negative));
    if (state.tracing) {
      fused.push_back(bigs_json(lanes));
      sops.push_back(sop.str());
    }
  }
  trace(state, "e_group_sum_and_abs",
        {{"lane_fused_tc", fused},
         {"sop_tc", sops},
         {"magnitude", bigs_json(state.e_frontend.group_magnitudes)},
         {"sign", state.e_frontend.group_negative},
         {"width", e_compact_group_bits},
         {"f", e_group_fraction_bits}});
}

void stage_scale(const Config &config, State &state, bool do_detect) {
  Json scale_trace = Json::array();
  for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
    Token out;
    out.width = config.group_mag_bits();
    out.negative = state.e_frontend.group_negative[group_index];
    const auto &scale_a = state.scale_a[group_index];
    const auto &scale_b = state.scale_b[group_index];
    out.special.nan = scale_a.category == Class::NaN || scale_b.category == Class::NaN;
    out.special.invalid = scale_a.signaling || scale_b.signaling;
    const Big &magnitude = state.e_frontend.group_magnitudes[group_index];
    if (state.request.a_type == DataType::MXFP4) {
      const unsigned pad = out.width - (e_compact_group_bits - 1);
      out.magnitude = magnitude << pad;
      out.fractional_bits = e_group_fraction_bits + pad;
    } else {
      const unsigned magnitude_bits = e_compact_group_bits - 1;
      const unsigned coefficient_bits = 2 * scale_magnitude_bits;
      const unsigned product_bits = magnitude_bits + coefficient_bits;
      const Big &coefficient = state.e_frontend.scale_coefficients[group_index];
      const Big product = magnitude * coefficient;
      check_unsigned(product, product_bits, "E S5 unsigned scale product");
      const unsigned pad = out.width - product_bits;
      out.magnitude = product << pad;
      out.fractional_bits = e_group_fraction_bits + 2 * scale_fraction_bits + pad;
      if (state.tracing)
        scale_trace.push_back({{"sop_magnitude_bits", magnitude_bits},
                               {"coefficient_bits", coefficient_bits},
                               {"product_bits", product_bits},
                               {"sop_magnitude", magnitude.str()},
                               {"coefficient", coefficient.str()},
                               {"product", product.str()}});
    }
    check_unsigned(out.magnitude, out.width, "E S5 token magnitude");
    const int alpha =
        state.e_frontend.scale_exponents[group_index] -
        (config.architecture_v19 ? 0 : 2 * static_cast<int>(scale_bias));
    out.anchor_raw =
        alpha - static_cast<int>(out.fractional_bits) + static_cast<int>(out.width) - 1;
    if (config.architecture_v19) {
      if (out.anchor_raw != state.group_raw_anchors.at(group_index))
        throw std::logic_error("E S3/S5 raw anchor mismatch");
      // The physical LZD consumes the U22 container, before structural low zeros.
      // MX is U14 << 8; NV/HiF are U14 * U8. Nonzero clz is unchanged by padding.
      constexpr unsigned scale_product_bits = e_compact_group_bits - 1 + 2 * scale_magnitude_bits;
      const Big lzd_magnitude = out.magnitude >> (out.width - scale_product_bits);
      const unsigned narrow_zero_count = clz(lzd_magnitude, scale_product_bits);
      if (out.active() && narrow_zero_count != clz(out.magnitude, out.width))
        throw std::logic_error("E U22/exported LZD mismatch");
      if (do_detect) {
        out.leading_zero_count = out.active() ? narrow_zero_count : 0;
        if (!out.active()) out.anchor_raw = 0;
        out.compare_exp = out.anchor_raw - static_cast<int>(out.leading_zero_count);
      }
      if (state.tracing)
        scale_trace.push_back({{"lzd_magnitude", lzd_magnitude.str()},
                               {"lzd_width", scale_product_bits},
                               {"leading_zero_count", narrow_zero_count},
                               {"raw_anchor_s3", state.group_raw_anchors.at(group_index)}});
    }
    state.groups.push_back(std::move(out));
  }
  finish_group_stage(state, do_detect, scale_trace, config.architecture_v19);
}
} // namespace dp::e_frontend
