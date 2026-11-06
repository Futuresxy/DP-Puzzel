#include "detail.hpp"
#include <stdexcept>

namespace dp {
Big mask(unsigned bits) { return (Big(1) << bits) - 1; }
Big abs_big(const Big &value) { return value < 0 ? Big(-value) : value; }
unsigned bit_length(const Big &value) {
  return value == 0 ? 0 : boost::multiprecision::msb(value) + 1;
}
unsigned clz(const Big &value, unsigned width) {
  check_unsigned(value, width, "LZD input");
  return value == 0
             ? 0
             : width - bit_length(value); // zero is separately masked, never a numeric exponent
}
void check_unsigned(const Big &value, unsigned width, const char *context) {
  if (value < 0 || value > (mask(width)))
    throw std::invalid_argument(std::string(context) + ": unsigned width overflow");
}
void check_signed(const Big &value, unsigned width, const char *context) {
  if (!width || value < -(Big(1) << (width - 1)) || value >= (Big(1) << (width - 1)))
    throw std::logic_error(std::string(context) + ": signed width overflow");
}
Big rtz(const Big &value, unsigned amount, bool &lost) {
  if (value < 0)
    throw std::logic_error("RTZ requires magnitude");
  if (amount >= bit_length(value)) {
    lost |= (value != 0);
    return 0;
  }
  Big shifted_magnitude = value >> amount;
  lost |= ((shifted_magnitude << amount) != value);
  return shifted_magnitude;
}
Big signed_value(const Big &magnitude, bool negative) {
  return negative ? Big(-magnitude) : magnitude;
}
unsigned slice(const Big &value, unsigned offset, unsigned width) {
  return ((value >> offset) & mask(width)).convert_to<unsigned>();
}
// TC reduction, L=ceil(log2(N)).
// Precision / signal | S | I   | F
// ------------------ | - | --- | -
// Each input         | 1 | i   | f
// Output             | 1 | i+L | f
Big tree_sum(std::vector<Big> values, unsigned width) {
  if (values.empty())
    throw std::logic_error("empty sum tree");
  for (const auto &value : values)
    check_signed(value, width, "tree leaf");
  while (values.size() > 1) {
    std::vector<Big> next;
    for (std::size_t pair_index = 0; pair_index < values.size(); pair_index += 2) {
      Big pair_sum = values[pair_index];
      if (pair_index + 1 < values.size())
        pair_sum += values[pair_index + 1];
      check_signed(pair_sum, width + 1, "tree node");
      next.push_back(pair_sum);
    }
    values = std::move(next);
    ++width;
  }
  return values.front();
}
namespace {
Big round_even(const Big &magnitude, int shift, bool &inexact) {
  if (shift <= 0)
    return magnitude << (-shift);
  Big quotient = magnitude >> shift;
  Big remainder = magnitude - (quotient << shift);
  Big halfway = Big(1) << (shift - 1);
  inexact |= remainder != 0;
  if (remainder > halfway || (remainder == halfway && static_cast<bool>(quotient & 1)))
    ++quotient;
  return quotient;
}
} // namespace
// Round a TC coefficient at the supplied LSB exponent.
// Rounded FP32 coefficient (unsigned).
// Precision / signal | S | I | F
// ------------------ | - | - | --
// FP32 coefficient   | 0 | 1 | 23
// The final FP32 output encodes sign/exponent/fraction with widths 1/8/23.
std::uint32_t round_fp32(const Big &value, int lsb_exponent, bool negative_zero, Flags &flags) {
  const bool negative = value < 0 || (value == 0 && negative_zero);
  const std::uint32_t sign = negative ? 0x80000000u : 0;
  const Big magnitude = abs_big(value);
  if (magnitude == 0)
    return sign;
  int exponent_value = lsb_exponent + static_cast<int>(bit_length(magnitude)) - 1;
  if (exponent_value >= -126) {
    Big significand = round_even(
        magnitude, static_cast<int>(bit_length(magnitude)) - static_cast<int>(fp32_magnitude_bits),
        flags.inexact);
    if (significand == (Big(1) << fp32_magnitude_bits)) {
      significand >>= 1;
      ++exponent_value;
    }
    if (exponent_value > 127) {
      flags.overflow = true;
      flags.inexact = true;
      return sign | 0x7f800000u;
    }
    return sign | (static_cast<std::uint32_t>(exponent_value + 127) << fp32_fraction_bits) |
           (significand & mask(fp32_fraction_bits)).convert_to<std::uint32_t>();
  }
  Big fraction = round_even(magnitude, -149 - lsb_exponent, flags.inexact);
  flags.underflow = flags.inexact && fraction < (Big(1) << fp32_fraction_bits);
  // Rounding a largest subnormal upward naturally sets exponent bit zero to one.
  return sign | fraction.convert_to<std::uint32_t>();
}
void Special::merge(const Special &other) {
  nan |= other.nan;
  invalid |= other.invalid;
  positive_inf |= other.positive_inf;
  negative_inf |= other.negative_inf;
  invalid |= positive_inf && negative_inf;
}
Special product_special(const Number &operand_a, const Number &operand_b) {
  Special special_flags;
  special_flags.nan = operand_a.category == Class::NaN || operand_b.category == Class::NaN;
  special_flags.invalid = operand_a.signaling || operand_b.signaling;
  bool inf = operand_a.category == Class::Inf || operand_b.category == Class::Inf;
  bool zero = operand_a.category == Class::Zero || operand_b.category == Class::Zero;
  special_flags.invalid |= inf && zero;
  if (inf && !zero && !special_flags.nan) {
    if (operand_a.negative != operand_b.negative)
      special_flags.negative_inf = true;
    else
      special_flags.positive_inf = true;
  }
  return special_flags;
}
void trace(State &state, const char *operation, Json data) {
  if (state.tracing)
    state.result.trace.push_back(
        {{"stage", state.stage}, {"operation", operation}, {"data", std::move(data)}});
}
Json special_json(const Special &value) {
  return {{"nan", value.nan},
          {"invalid", value.invalid},
          {"positive_inf", value.positive_inf},
          {"negative_inf", value.negative_inf}};
}
Json number_json(const Number &number) {
  return {{"sign", number.negative},
          {"m", number.magnitude.str()},
          {"e", number.exponent},
          {"f", number.fractional_bits},
          {"class", static_cast<int>(number.category)},
          {"signaling", number.signaling}};
}
Json token_json(const Token &token) {
  return {{"sign", token.negative},
          {"m", token.magnitude.str()},
          {"width", token.width},
          {"f", token.fractional_bits},
          {"anchor_raw", token.anchor_raw},
          {"z", token.leading_zero_count},
          {"e", token.anchor_raw - static_cast<int>(token.leading_zero_count)},
          {"zero", token.magnitude == 0},
          {"special", special_json(token.special)}};
}
Json bigs_json(const std::vector<Big> &values) {
  Json encoded_values = Json::array();
  for (const auto &value : values)
    encoded_values.push_back(value.str());
  return encoded_values;
}
} // namespace dp
