#include "detail.hpp"
#include <array>

namespace dp {
namespace {
Number binary(unsigned raw_encoding, unsigned exponent_field_width, unsigned fraction_field_width,
              unsigned bias, bool ieee_special, bool finite_e4m3) {
  Number number;
  number.negative = (raw_encoding >> (exponent_field_width + fraction_field_width)) & 1;
  const unsigned exponent_field =
      (raw_encoding >> fraction_field_width) & ((1u << exponent_field_width) - 1);
  const unsigned fraction_field = raw_encoding & ((1u << fraction_field_width) - 1);
  number.fractional_bits = fraction_field_width;
  number.exponent = exponent_field ? static_cast<int>(exponent_field) : 1;
  const bool special = exponent_field == ((1u << exponent_field_width) - 1);
  if ((ieee_special && special && fraction_field) ||
      (finite_e4m3 && special && fraction_field == ((1u << fraction_field_width) - 1))) {
    number.category = Class::NaN;
    number.signaling = ieee_special && !(fraction_field & (1u << (fraction_field_width - 1)));
    number.exponent = 1;
    return number;
  }
  if (ieee_special && special && !fraction_field) {
    number.category = Class::Inf;
    number.exponent = 1;
    return number;
  }
  number.magnitude = (exponent_field ? (1u << fraction_field_width) : 0) | fraction_field;
  number.category = number.magnitude == 0 ? Class::Zero : Class::Finite;
  (void)bias;
  return number;
}
Json layout(const std::vector<Number> &values, DataType type) {
  Json atoms = Json::array();
  const auto &format_info = format(type);
  const unsigned per_atom = type == DataType::TF32 ? 1 : format_info.lane_elements / 2;
  for (unsigned atom_start_index = 0; atom_start_index < values.size();
       atom_start_index += per_atom) {
    unsigned packed_exponents = 0;
    unsigned packed_mantissas = 0;
    unsigned packed_signs = 0;
    for (unsigned slot_index = 0; slot_index < per_atom; ++slot_index) {
      const auto &number = values[atom_start_index + slot_index];
      unsigned mantissa = number.magnitude.convert_to<unsigned>();
      if (type == DataType::INT8)
        packed_mantissas |= mantissa << (8 * slot_index);
      else if (format_info.lane_elements >= 4)
        packed_mantissas |= mantissa << (4 * slot_index);
      else
        packed_mantissas = mantissa;
      packed_signs |= unsigned(number.negative) << slot_index;
      if (type == DataType::HIF4)
        packed_exponents = static_cast<unsigned>(number.exponent);
      else if (format_info.lane_elements == 4 && type != DataType::INT8)
        packed_exponents |= static_cast<unsigned>(number.exponent) << (5 * slot_index);
      else if (format_info.lane_elements < 4)
        packed_exponents = static_cast<unsigned>(number.exponent);
    }
    atoms.push_back({{"E", packed_exponents}, {"M", packed_mantissas}, {"S", packed_signs}});
  }
  return atoms;
}
} // namespace
// S1 logical operand output (SM). Sign and exponent are separate.
// Precision / signal | S | I | F
// ------------------ | - | - | --
// TF32 / FP16        | 1 | 1 | 10
// BF16               | 1 | 1 | 7
// MXFP8 / MXFP6      | 1 | 1 | 3
// MXFP4 / NVFP4      | 1 | 3 | 1
// HiF4               | 1 | 2 | 2
// INT8               | 1 | 8 | 0
Number unpack_element(DataType type, unsigned raw_encoding, unsigned e1, unsigned e2) {
  const auto &format_info = format(type);
  Number number;
  if (type == DataType::INT8) {
    number.negative = (raw_encoding & 128) != 0;
    number.magnitude = number.negative ? 256 - raw_encoding : raw_encoding;
  } else if (type == DataType::HIF4) {
    number.negative = (raw_encoding & 8) != 0;
    number.magnitude = (raw_encoding & 7) << e1;
    number.exponent = e2;
    number.fractional_bits = 2;
  } else if (type == DataType::MXFP4 || type == DataType::NVFP4) {
    constexpr std::array<unsigned, 8> fp4_coefficients{{0, 1, 2, 3, 4, 6, 8, 12}};
    number.negative = (raw_encoding & 8) != 0;
    number.magnitude = fp4_coefficients[raw_encoding & 7];
    number.fractional_bits = 1;
  } else {
    if (type == DataType::TF32)
      raw_encoding >>= 13;
    if (type == DataType::MXFP6_E3M2 || type == DataType::MXFP6_E2M3)
      raw_encoding >>= 2;
    const bool ieee = type == DataType::TF32 || type == DataType::FP16 || type == DataType::BF16 ||
                      type == DataType::MXFP8_E5M2;
    number = binary(raw_encoding, format_info.exponent_bits, format_info.fraction_bits,
                    format_info.bias, ieee, type == DataType::MXFP8_E4M3);
    if (format_info.lane_elements == q_elements_per_lane) {
      if (number.category != Class::NaN && number.category != Class::Inf)
        number.exponent += 15 - static_cast<int>(format_info.bias);
      number.magnitude <<= scale_fraction_bits - format_info.fraction_bits;
      number.fractional_bits = scale_fraction_bits;
    }
    return number;
  }
  number.category = number.magnitude == 0 ? Class::Zero : Class::Finite;
  return number;
}
// Unsigned scale output. The biased exponent is separate.
// Precision / signal | S | I | F
// ------------------ | - | - | -
// E8M0               | 0 | 1 | 3
// E4M3               | 0 | 1 | 3
// E6M2               | 0 | 1 | 3
// Unit scale         | 0 | 1 | 3
Number unpack_scale(ScaleType type, unsigned raw_encoding) {
  Number number;
  number.exponent = scale_bias;
  number.fractional_bits = scale_fraction_bits;
  if (type == ScaleType::NONE)
    number.magnitude = 1u << scale_fraction_bits;
  else if (type == ScaleType::E8M0) {
    if (raw_encoding == 255) {
      number.category = Class::NaN;
      return number;
    }
    number.exponent = raw_encoding;
    number.magnitude = 1u << scale_fraction_bits;
  } else if (type == ScaleType::E6M2) {
    if (raw_encoding == 255) {
      number.category = Class::NaN;
      return number;
    }
    number.exponent = static_cast<int>(raw_encoding >> 2) + 127 - 48;
    number.magnitude = (4 + (raw_encoding & 3)) << 1;
  } else {
    number = binary(raw_encoding, 4, 3, 7, false, true);
    if (number.category != Class::NaN)
      number.exponent += 127 - 7;
  }
  if (number.category != Class::NaN)
    number.category = number.magnitude == 0 ? Class::Zero : Class::Finite;
  return number;
}
// S5 C token (SM). FP32 appends 8 low zeros; sign is separate.
// Precision / signal | S | I  | F
// ------------------ | - | -- | --
// FP32               | 1 | 1  | 31
// INT32              | 1 | 32 | 0
Token unpack_c(CType type, std::uint32_t raw_encoding) {
  Token token;
  token.width = int32_bits;
  if (type == CType::INT32) {
    Big value = raw_encoding;
    if (raw_encoding & 0x80000000u)
      value -= Big(1) << int32_bits;
    token.negative = value < 0;
    token.magnitude = abs_big(value);
    return token;
  }
  const auto number = binary(raw_encoding, 8, fp32_fraction_bits, 127, true, false);
  token.negative = number.negative;
  token.magnitude = number.magnitude << (int32_bits - fp32_magnitude_bits);
  token.fractional_bits = int32_bits - 1;
  token.anchor_raw = number.exponent - 127;
  token.special.nan = number.category == Class::NaN;
  token.special.invalid = number.signaling;
  if (number.category == Class::Inf) {
    token.special.positive_inf = !number.negative;
    token.special.negative_inf = number.negative;
  }
  return token;
}
void stage_unpack(const Config &config, State &state) {
  const auto &request = state.request;
  const auto &format_info = format(request.a_type);
  for (unsigned element_index = 0; element_index < config.elements(request.a_type);
       ++element_index) {
    auto unpack_operand = [&](const Big &data, const Big &e1, const Big &e2) {
      return unpack_element(
          request.a_type,
          slice(data, element_index * format_info.storage_bits, format_info.storage_bits),
          slice(e1, element_index / 4, 1), slice(e2, element_index / 8, 1));
    };
    state.operands_a.push_back(unpack_operand(request.a, request.a_e1, request.a_e2));
    state.operands_b.push_back(unpack_operand(request.b, request.b_e1, request.b_e2));
  }
  for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
    state.scale_a.push_back(
        unpack_scale(request.a_scale_type, slice(request.a_scale, group_index * 8, 8)));
    state.scale_b.push_back(
        unpack_scale(request.b_scale_type, slice(request.b_scale, group_index * 8, 8)));
  }
  if (state.tracing) {
    Json operands_a_json = Json::array();
    Json operands_b_json = operands_a_json;
    Json scales_a_json = operands_a_json;
    Json scales_b_json = operands_a_json;
    for (const auto &number : state.operands_a)
      operands_a_json.push_back(number_json(number));
    for (const auto &number : state.operands_b)
      operands_b_json.push_back(number_json(number));
    for (const auto &number : state.scale_a)
      scales_a_json.push_back(number_json(number));
    for (const auto &number : state.scale_b)
      scales_b_json.push_back(number_json(number));
    trace(state, "unpack",
          {{"a", operands_a_json},
           {"b", operands_b_json},
           {"a_layout", layout(state.operands_a, request.a_type)},
           {"b_layout", layout(state.operands_b, request.b_type)},
           {"scale_a", scales_a_json},
           {"scale_b", scales_b_json},
           {"c_raw", request.c}});
  }
}
} // namespace dp
