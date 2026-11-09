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
  token.compare_exp = token.anchor_raw - static_cast<int>(token.leading_zero_count);
}
void finish_group_stage(State &state, bool do_detect, const Json &scale_trace,
                        bool groups_already_detected) {
  if (do_detect && !groups_already_detected && state.request.c_type == CType::FP32)
    for (auto &group : state.groups)
      detect_token(group);
  state.c_token = unpack_c(state.request.c_type, state.request.c);
  if (do_detect && state.request.c_type == CType::FP32 && !state.baseline_v18)
    detect_token(state.c_token);
  if (state.baseline_v18) {
    // No C LZD, but inactive tokens still carry the same zero placeholder as RTL.
    if (!state.c_token.active()) state.c_token.anchor_raw = 0;
    state.c_token.compare_exp = state.c_token.anchor_raw;
  }
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
    if (!state.baseline_v18) detect_token(state.c_token);
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
  std::vector<bool> participate = state.participate;
  if (participate.empty()) participate.assign(state.groups.size(), true);
  participate.push_back(true); // C always participates, including its zero sign.
  bool any = false;
  state.common = 0;
  if (!integer)
    for (unsigned source_index = 0; source_index < sources.size(); ++source_index) {
      const auto &token = sources[source_index];
      if (participate[source_index] && token.active()) {
        const int exponent_value = state.baseline_v18 ? token.compare_exp :
            token.anchor_raw - static_cast<int>(token.leading_zero_count);
        state.common = any ? std::max(state.common, exponent_value) : exponent_value;
        any = true;
      }
    }
  Json controls = Json::array();
  state.negative_zero = true;
  for (unsigned source_index = 0; source_index < sources.size(); ++source_index) {
    const auto &token = sources[source_index];
    if (!participate[source_index]) {
      state.aligned.push_back(0);
      controls.push_back({{"d", 0}, {"net", 0}, {"z", 0}, {"participate", false}});
      continue;
    }
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
  Json carry_save = Json::object();
  if (config.mixed()) {
    std::vector<Big> base(state.aligned.begin(), state.aligned.begin() + 4);
    base.push_back(state.aligned.back());
    const std::vector<Big> extension(state.aligned.begin() + 4, state.aligned.end() - 1);
    const Big base_sum = tree_sum(base, config.global_signed_align_width);
    const Big extension_sum = tree_sum(extension, config.global_signed_align_width);
    state.sum = base_sum;
    if (config.extension_supports(state.request.a_type)) state.sum += extension_sum;
  } else state.sum = tree_sum(state.aligned, config.global_signed_align_width);
  check_signed(state.sum, config.sum_bits(), "final sum");
  if (config.architecture_v19 && state.groups.size() >= 4) {
    // Carry rows include their left shift. Each row is a W-bit residue, not an
    // independently signed subtotal. Only the final CPA is interpreted as TC.
    const unsigned width = config.sum_bits();
    const Big word_mask = mask(width);
    const Big modulus = Big(1) << width;
    const auto word = [&word_mask](const Big &value) -> Big { return value & word_mask; };
    using Rows = std::pair<Big, Big>;
    const auto compress_three = [&word_mask](const Big &first, const Big &second,
                                            const Big &third) -> Rows {
      return {(first ^ second ^ third) & word_mask,
              (((first & second) | (first & third) | (second & third)) << 1) & word_mask};
    };
    const auto compress_four = [&compress_three](const Big &first, const Big &second,
                                                const Big &third, const Big &fourth) -> Rows {
      const auto partial = compress_three(first, second, third);
      return compress_three(partial.first, partial.second, fourth);
    };
    const auto base_groups = compress_four(word(state.aligned[0]), word(state.aligned[1]),
                                          word(state.aligned[2]), word(state.aligned[3]));
    const auto base_rows = compress_three(base_groups.first, base_groups.second,
                                         word(state.aligned.back()));
    Rows selected_rows = base_rows;
    const bool extension_active = config.mixed() && config.extension_supports(state.request.a_type);
    if (extension_active && config.groups() == 6)
      selected_rows = compress_four(base_rows.first, base_rows.second,
                                    word(state.aligned[4]), word(state.aligned[5]));
    else if (extension_active && config.groups() == 8) {
      const auto extension_rows = compress_four(word(state.aligned[4]), word(state.aligned[5]),
                                               word(state.aligned[6]), word(state.aligned[7]));
      selected_rows = compress_four(base_rows.first, base_rows.second,
                                    extension_rows.first, extension_rows.second);
    }
    Big cpa_residue = (selected_rows.first + selected_rows.second) & word_mask;
    const Big cpa_signed = cpa_residue >= (Big(1) << (width - 1)) ? cpa_residue - modulus
                                                               : cpa_residue;
    if (cpa_signed != state.sum)
      throw std::logic_error("carry-save/final exact sum mismatch");
    carry_save = {{"sum_row", selected_rows.first.str()},
                  {"carry_row", selected_rows.second.str()},
                  {"width", width}, {"extension_active", extension_active},
                  {"carry_already_shifted", true}};
  }
  Json total_trace =
      {{"sop_tc", state.sum.str()},
       {"width", config.sum_bits()},
       {"f", state.request.c_type == CType::INT32 ? config.global_mag_bits() - int32_bits
                                                 : config.global_mag_bits() - 1},
       {"E_max", state.common}};
  if (!carry_save.empty()) total_trace["carry_save"] = std::move(carry_save);
  trace(state, "total_sop_tree",
        total_trace);
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
    for (unsigned group_index = 0; group_index < state.groups.size(); ++group_index)
      if (state.participate.empty() || state.participate[group_index])
        all.merge(state.groups[group_index].special);
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
