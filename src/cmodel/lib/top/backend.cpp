#include "detail.hpp"
#include <algorithm>

// Shared S5 token completion/C decode and S6-S8. Both frontends call these
// exact stage functions; the source coordinate is always carried in Token.
namespace dp {
void detect_token(Token &token) {
  if (token.active())
    token.leading_zero_count = clz(token.magnitude, token.width);
  else {
    token.leading_zero_count = 0;
    token.anchor_raw = 0;
  }
}
void finish_group_stage(State &state, bool do_detect, const Json &scale_trace) {
  if (do_detect && state.request.c_type == CType::FP32)
    for (auto &group : state.groups)
      detect_token(group);
  state.c_token = unpack_c(state.request.c_type, state.request.c);
  if (do_detect && state.request.c_type == CType::FP32)
    detect_token(state.c_token);
  if (state.tracing) {
    Json group = Json::array();
    for (const auto &token : state.groups)
      group.push_back(token_json(token));
    trace(state, do_detect ? "group_abs_scale_LZD_and_C" : "group_abs_scale_and_C",
          {{"groups", group}, {"c", token_json(state.c_token)}, {"scale_multiplier", scale_trace}});
  }
}
void stage_detect(const Config &, State &state) {
  if (state.request.c_type == CType::FP32) {
    for (auto &token : state.groups)
      detect_token(token);
    detect_token(state.c_token);
  }
  if (state.tracing) {
    Json group = Json::array();
    for (const auto &token : state.groups)
      group.push_back(token_json(token));
    trace(state, "extra_LZD_register", {{"groups", group}, {"c", token_json(state.c_token)}});
  }
}
// S6 pad=global_mag_bits()-source.width. Let M=global_mag_bits().
// Unsigned aligned magnitude -> TC leaf. Both use the listed I/F.
// Precision          | Mag S | Leaf S | I  | F
// ------------------ | ----- | ------ | -- | ----
// All floating modes | 0     | 1      | 1  | M-1
// INT8 + INT32       | 0     | 1      | 32 | M-32
// Floating coordinates use E_max. Integers use structural low zeros.
void stage_global_align(const Config &config, State &state) {
  std::vector<Token> sources = state.groups;
  sources.push_back(state.c_token);
  const bool integer = state.request.c_type == CType::INT32;
  bool any = false;
  state.common = 0;
  if (!integer)
    for (const auto &token : sources)
      if (token.active()) {
        const int exponent_value = token.anchor_raw - static_cast<int>(token.leading_zero_count);
        state.common = any ? std::max(state.common, exponent_value) : exponent_value;
        any = true;
      }
  Json controls = Json::array();
  state.negative_zero = true;
  for (const auto &token : sources) {
    Big magnitude = 0;
    int delta = 0;
    int net_shift = 0;
    if (integer) {
      if (token.magnitude % (Big(1) << token.fractional_bits) != 0)
        throw std::logic_error("integer lost structural bits");
      magnitude = (token.magnitude >> token.fractional_bits)
                  << (config.global_mag_bits() - int32_bits);
    } else if (token.active()) {
      delta = state.common - (token.anchor_raw - static_cast<int>(token.leading_zero_count));
      net_shift = token.anchor_raw - state.common;
      if (delta < 0 || net_shift != static_cast<int>(token.leading_zero_count) - delta ||
          net_shift > static_cast<int>(token.leading_zero_count))
        throw std::logic_error("invalid fused shift relation");
      Big padded_magnitude = token.magnitude << (config.global_mag_bits() - token.width);
      if (net_shift >= 0)
        magnitude = padded_magnitude << net_shift;
      else
        magnitude = rtz(padded_magnitude, -net_shift, state.result.flags.global_truncated);
    }
    check_unsigned(magnitude, config.global_mag_bits(), "global shift output");
    state.aligned.push_back(signed_value(magnitude, token.negative));
    state.negative_zero &= (magnitude == 0 && token.negative);
    controls.push_back({{"d", delta}, {"net", net_shift}, {"z", token.leading_zero_count}});
  }
  trace(state, "global_max_and_bidirectional_align",
        {{"E_max", state.common},
         {"controls", controls},
         {"aligned_tc", bigs_json(state.aligned)},
         {"width", config.global_signed_align_width},
         {"f", integer ? config.global_mag_bits() - int32_bits : config.global_mag_bits() - 1}});
}
// K=c.k_fp16, G=K/4, L=ceil(log2(G+1)), W=c.global_signed_align_width.
// S7 total SOP (TC).
// Precision / signal | S | I    | F
// ------------------ | - | ---- | ----
// All floating modes | 1 | 1+L  | W-2
// INT8 + INT32       | 1 | 32+L | W-33
void stage_total(const Config &config, State &state) {
  state.sum = tree_sum(state.aligned, config.global_signed_align_width);
  check_signed(state.sum, config.sum_bits(), "final sum");
  trace(state, "total_sop_tree",
        {{"sop_tc", state.sum.str()},
         {"width", config.sum_bits()},
         {"f", state.request.c_type == CType::INT32 ? config.global_mag_bits() - int32_bits
                                                    : config.global_mag_bits() - 1},
         {"E_max", state.common}});
}
// S8 result formats.
// Precision / signal | S | I  | F
// ------------------ | - | -- | --
// FP32 coefficient   | 0 | 1  | 23
// INT32 output (TC)  | 1 | 31 | 0
// The final FP32 output encodes sign/exponent/fraction with widths 1/8/23.
void stage_output(const Config &config, State &state) {
  auto &result = state.result;
  result.id = state.request.id;
  result.type = state.request.c_type;
  result.last = state.request.last;
  if (result.type == CType::INT32) {
    Big value = state.sum / (Big(1) << (config.global_mag_bits() - int32_bits));
    result.flags.integer_overflow =
        value < -(Big(1) << (int32_bits - 1)) || value >= (Big(1) << (int32_bits - 1));
    Big residue = value % (Big(1) << int32_bits);
    if (residue < 0)
      residue += Big(1) << int32_bits;
    result.bits = residue.convert_to<std::uint32_t>();
  } else {
    Special all = state.c_token.special;
    for (const auto &group_token : state.groups)
      all.merge(group_token.special);
    result.flags.invalid = all.invalid;
    if (all.nan || all.invalid)
      result.bits = canonical_nan;
    else if (all.positive_inf || all.negative_inf)
      result.bits = all.negative_inf ? 0xff800000u : 0x7f800000u;
    else
      result.bits =
          round_fp32(state.sum, state.common - static_cast<int>(config.global_mag_bits() - 1),
                     state.negative_zero, result.flags);
  }
  trace(
      state, "output",
      {{"bits", result.bits}, {"type", static_cast<unsigned>(result.type)}, {"last", result.last}});
}
} // namespace dp
