#include "detail.hpp"
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace dp {
namespace {
std::uint64_t unsigned_json(const Json &json_value, const char *key) {
  const auto &value = json_value.at(key);
  if (!value.is_number_integer() || (!value.is_number_unsigned() && value.get<std::int64_t>() < 0))
    throw std::invalid_argument(std::string(key) + " must be a nonnegative integer");
  return value.get<std::uint64_t>();
}
unsigned field(const Json &json_value, const char *key) {
  const auto value = unsigned_json(json_value, key);
  if (value > std::numeric_limits<unsigned>::max())
    throw std::invalid_argument(std::string(key) + " exceeds unsigned range");
  return static_cast<unsigned>(value);
}
Big hex_value(const Json &json_value, const char *key) {
  const auto text = json_value.at(key).get<std::string>();
  if (text.empty() || text.find_first_not_of("0123456789abcdefABCDEF") != std::string::npos)
    throw std::invalid_argument(std::string(key) + " must be unsigned hex without 0x prefix");
  return Big("0x" + text);
}
} // namespace
Config config_from_json(const Json &json_value) {
  Config config;
  for (auto field_iterator = json_value.begin(); field_iterator != json_value.end();
       ++field_iterator) {
    const auto &key = field_iterator.key();
    if (key == "k_fp16")
      config.k_fp16 = field(json_value, key.c_str());
    else if (key == "local_shift_mag_width")
      config.local_shift_mag_width = field(json_value, key.c_str());
    else if (key == "global_signed_align_width")
      config.global_signed_align_width = field(json_value, key.c_str());
    else if (key == "post_scale_norm_extra_stage")
      config.post_scale_norm_extra_stage = field(json_value, key.c_str());
    else if (key == "frontend") {
      const auto value = field_iterator.value().get<std::string>();
      if (value == "multi")
        config.frontend = Frontend::Multi;
      else if (value == "e")
        config.frontend = Frontend::E;
      else if (value == "qe") config.frontend = Frontend::QE;
      else if (value == "t8h16q32e96") config.frontend = Frontend::MixedE96;
      else if (value == "t8h16q32e128") config.frontend = Frontend::MixedE128;
      else if (value == "t8h16q64e128") config.frontend = Frontend::MixedQE128;
      else throw std::invalid_argument("unknown frontend profile");
    } else
      throw std::invalid_argument("unknown configuration key: " + key);
  }
  config.validate();
  return config;
}
Request request_from_json(const Json &json_value) {
  Request request;
  request.id = unsigned_json(json_value, "id");
  request.a_type = static_cast<DataType>(field(json_value, "a_datatype"));
  request.b_type = static_cast<DataType>(field(json_value, "b_datatype"));
  request.c_type = static_cast<CType>(field(json_value, "c_datatype"));
  request.a_scale_type = static_cast<ScaleType>(field(json_value, "a_scale_datatype"));
  request.b_scale_type = static_cast<ScaleType>(field(json_value, "b_scale_datatype"));
  request.last = json_value.at("last").get<bool>();
  request.a = hex_value(json_value, "a");
  request.b = hex_value(json_value, "b");
  auto c_bits = hex_value(json_value, "c");
  check_unsigned(c_bits, int32_bits, "C payload");
  request.c = c_bits.convert_to<std::uint32_t>();
  request.a_scale = hex_value(json_value, "a_scale");
  request.b_scale = hex_value(json_value, "b_scale");
  request.a_e1 = hex_value(json_value, "a_e1");
  request.a_e2 = hex_value(json_value, "a_e2");
  request.b_e1 = hex_value(json_value, "b_e1");
  request.b_e2 = hex_value(json_value, "b_e2");
  return request;
}
Json config_json(const Config &config) {
  Json result = {{"frontend", name(config.frontend)},
                 {"k_fp16", config.k_fp16},
                 {"local_shift_mag_width", config.local_shift_mag_width},
                 {"global_signed_align_width", config.global_signed_align_width},
                 {"post_scale_norm_extra_stage", config.post_scale_norm_extra_stage},
                 {"latency", config.latency()},
                 {"groups", config.groups()},
                 {"leaf_bits", config.leaf_bits()},
                 {"lane_bits", config.lane_bits()},
                 {"group_mag_bits", config.group_mag_bits()},
                 {"sum_bits", config.sum_bits()}};
  if (config.frontend == Frontend::E) {
    result.erase("leaf_bits");
    result["pair_bits"] = config.leaf_bits();
    result["group_internal_mag_bits"] = e_compact_group_bits - 1;
    result["k_e"] = config.elements(DataType::MXFP4);
  }
  return result;
}
Json result_json(const Result &request) {
  std::ostringstream hex;
  hex << std::hex << std::setfill('0') << std::setw(8) << request.bits;
  Json json_value = {{"id", request.id},
                     {"d", hex.str()},
                     {"d_datatype", static_cast<unsigned>(request.type)},
                     {"last", request.last},
                     {"flags",
                      {{"invalid", request.flags.invalid},
                       {"overflow", request.flags.overflow},
                       {"underflow", request.flags.underflow},
                       {"inexact", request.flags.inexact},
                       {"integer_overflow", request.flags.integer_overflow},
                       {"local_truncated", request.flags.local_truncated},
                       {"global_truncated", request.flags.global_truncated}}}};
  if (!request.trace.empty())
    json_value["trace"] = request.trace;
  return json_value;
}
Json tick_json(const Tick &tick) {
  Json json_value = {{"ready_a", tick.ready},
                     {"ready_b", tick.ready},
                     {"ready_c", tick.ready},
                     {"accepted", tick.accepted},
                     {"valid", tick.output.has_value()},
                     {"protocol_error", tick.protocol_error}};
  if (tick.output)
    json_value["result"] = result_json(*tick.output);
  if (!tick.registers.empty())
    json_value["registers_after_edge"] = tick.registers;
  return json_value;
}
} // namespace dp
