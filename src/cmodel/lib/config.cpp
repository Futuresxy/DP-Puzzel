#include "detail.hpp"
#include <array>
#include <limits>
#include <stdexcept>

namespace dp {
namespace {
constexpr std::array<Format, 11> formats{{{32, 8, 10, 127, 1, ScaleType::NONE},
                                          {16, 5, 10, 15, 2, ScaleType::NONE},
                                          {16, 8, 7, 127, 2, ScaleType::NONE},
                                          {8, 4, 3, 7, 4, ScaleType::E8M0},
                                          {8, 5, 2, 15, 4, ScaleType::E8M0},
                                          {8, 3, 2, 3, 4, ScaleType::E8M0},
                                          {8, 2, 3, 1, 4, ScaleType::E8M0},
                                          {4, 2, 1, 1, 8, ScaleType::E8M0},
                                          {4, 2, 1, 1, 8, ScaleType::E4M3},
                                          {4, 0, 2, 0, 8, ScaleType::E6M2},
                                          {8, 0, 0, 0, 4, ScaleType::NONE}}};
constexpr std::array<const char *, 11> names{{"tf32", "fp16", "bf16", "mxfp8_e4m3", "mxfp8_e5m2",
                                              "mxfp6_e3m2", "mxfp6_e2m3", "mxfp4_e2m1", "nvfp4",
                                              "hif4", "int8"}};
} // namespace
const Format &format(DataType type) {
  auto element_index = static_cast<unsigned>(type);
  if (element_index >= formats.size())
    throw std::invalid_argument("reserved datatype");
  return formats[element_index];
}
const char *name(DataType datatype) {
  (void)format(datatype);
  return names[static_cast<unsigned>(datatype)];
}
const char *name(Frontend frontend) {
  switch (frontend) {
  case Frontend::Multi: return "multi";
  case Frontend::E: return "e";
  case Frontend::QE: return "qe";
  case Frontend::MixedE96: return "t8h16q32e96";
  case Frontend::MixedE128: return "t8h16q32e128";
  case Frontend::MixedQE128: return "t8h16q64e128";
  }
  throw std::invalid_argument("unknown frontend");
}
bool Config::extension_supports(DataType datatype) const {
  return datatype >= (frontend == Frontend::MixedQE128 ? DataType::MXFP8_E4M3
                                                      : DataType::MXFP4) &&
         datatype <= DataType::HIF4;
}
Frontend Config::group_frontend(unsigned group_index) const {
  if (!mixed()) return frontend;
  if (group_index < 4) return Frontend::Multi;
  return frontend == Frontend::MixedQE128 ? Frontend::QE : Frontend::E;
}
unsigned ceil_log2(unsigned element_count) {
  if (!element_count)
    throw std::invalid_argument("empty tree");
  unsigned tree_levels = 0;
  for (--element_count; element_count; element_count >>= 1)
    ++tree_levels;
  return tree_levels;
}
void Config::validate() const {
  if (static_cast<unsigned>(frontend) > static_cast<unsigned>(Frontend::MixedQE128))
    throw std::invalid_argument("unknown frontend");
  if (mixed() && (k_fp16 != 16 || post_scale_norm_extra_stage != 0))
    throw std::invalid_argument("mixed profiles require base K16 and L8");
  if (k_fp16 != 4 && k_fp16 != 8 && k_fp16 != 16)
    throw std::invalid_argument("k_fp16 must be 4,8,16");
  if (local_shift_mag_width < 27)
    throw std::invalid_argument("local window requires F>=25");
  if (local_shift_mag_width > static_cast<unsigned>(std::numeric_limits<int>::max() / 4) ||
      global_signed_align_width > static_cast<unsigned>(std::numeric_limits<int>::max() / 4))
    throw std::invalid_argument("parameter exceeds software exponent/index representation");
  if (global_signed_align_width <= std::max(group_mag_bits(), int32_bits))
    throw std::invalid_argument("global magnitude window too small for input slots");
  if (post_scale_norm_extra_stage > 1)
    throw std::invalid_argument("only L8/L9 profiles supported");
}
unsigned Config::lane_fraction(DataType datatype) const {
  if (frontend == Frontend::E) {
    if (datatype != DataType::MXFP4 && datatype != DataType::NVFP4 && datatype != DataType::HIF4)
      throw std::invalid_argument("unsupported E frontend datatype");
    return architecture_v19 || datatype == DataType::HIF4 ? 4 : 2;
  }
  const auto element_count = format(datatype).lane_elements;
  if (datatype == DataType::INT8)
    return lane_bits() - (int_product_bits + ceil_log2(element_count));
  if (element_count == e_elements_per_lane && baseline_v18())
    return e_group_fraction_bits + lane_bits() - e_lane_fused_bits;
  if (element_count == e_elements_per_lane) {
    const unsigned natural = e_pair_bits + e_guard_bits + ceil_log2(element_count / 2);
    const unsigned product_f = datatype == DataType::HIF4 ? 4 : 2;
    return product_f + e_guard_bits + lane_bits() - natural;
  }
  return local_fraction() + ceil_log2(q_elements_per_lane) - ceil_log2(element_count);
}
bool tuple_legal(const Request &request) {
  const auto a_datatype_code = static_cast<unsigned>(request.a_type);
  const auto b_datatype_code = static_cast<unsigned>(request.b_type);
  if (a_datatype_code >= formats.size() || a_datatype_code != b_datatype_code)
    return false;
  return request.c_type == (request.a_type == DataType::INT8 ? CType::INT32 : CType::FP32) &&
         request.a_scale_type == format(request.a_type).scale &&
         request.b_scale_type == format(request.b_type).scale;
}
bool tuple_legal(const Config &config, const Request &request) {
  return tuple_legal(request) &&
         (config.frontend == Frontend::Multi || config.mixed() ||
          (config.frontend == Frontend::QE && request.a_type >= DataType::MXFP8_E4M3 &&
           request.a_type <= DataType::HIF4) ||
          (config.frontend == Frontend::E &&
           (request.a_type == DataType::MXFP4 || request.a_type == DataType::NVFP4 ||
            request.a_type == DataType::HIF4)));
}
void validate_payload(const Config &config, const Request &request) {
  if (!tuple_legal(config, request))
    throw std::invalid_argument("illegal datatype tuple for frontend");
  check_unsigned(request.a, config.packed_bits(), "packed A");
  check_unsigned(request.b, config.packed_bits(), "packed B");
  check_unsigned(request.a_scale, 8 * config.groups(), "A scales");
  check_unsigned(request.b_scale, 8 * config.groups(), "B scales");
  check_unsigned(request.a_e1, 4 * config.groups(), "A e1");
  check_unsigned(request.b_e1, 4 * config.groups(), "B e1");
  check_unsigned(request.a_e2, 2 * config.groups(), "A e2");
  check_unsigned(request.b_e2, 2 * config.groups(), "B e2");
  const auto datatype = request.a_type;
  const auto &format_info = format(datatype);
  for (const Big *data : {&request.a, &request.b})
    for (unsigned element_index = 0; element_index < config.elements(datatype); ++element_index) {
      unsigned raw =
          slice(*data, element_index * format_info.storage_bits, format_info.storage_bits);
      if (datatype == DataType::TF32 && (raw & ((1u << 13) - 1)))
        throw std::invalid_argument("TF32 low13 must be zero");
      if ((datatype == DataType::MXFP6_E3M2 || datatype == DataType::MXFP6_E2M3) && (raw & 3))
        throw std::invalid_argument("FP6 low2 must be zero");
    }
  const unsigned active_groups = config.active_groups(datatype);
  if (datatype != DataType::HIF4 &&
      ((request.a_e1 & mask(4 * active_groups)) != 0 ||
       (request.a_e2 & mask(2 * active_groups)) != 0 ||
       (request.b_e1 & mask(4 * active_groups)) != 0 ||
       (request.b_e2 & mask(2 * active_groups)) != 0))
    throw std::invalid_argument("unused HiF metadata must be zero");
  if (format_info.scale == ScaleType::NONE && ((request.a_scale & mask(8 * active_groups)) != 0 ||
       (request.b_scale & mask(8 * active_groups)) != 0))
    throw std::invalid_argument("unused scales must be zero");
  for (const Big *data : {&request.a_scale, &request.b_scale})
    for (unsigned group_index = 0; group_index < active_groups; ++group_index) {
      const unsigned raw = slice(*data, group_index * 8, 8);
      if (datatype == DataType::NVFP4 && (raw & 128))
        throw std::invalid_argument("NV scale must be nonnegative");
      const unsigned first = (datatype == DataType::MXFP4) ? (group_index / 2) * 2 : (group_index / 4) * 4;
      if ((format_info.scale == ScaleType::E8M0 || datatype == DataType::HIF4) &&
          raw != slice(*data, first * 8, 8))
        throw std::invalid_argument("scale broadcast mismatch");
    }
}
} // namespace dp
