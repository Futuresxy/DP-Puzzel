#include "detail.hpp"
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <limits>

namespace dp {
namespace {
std::uint64_t unsigned_json(const Json& j,const char* key) {
  const auto& value=j.at(key);
  if(!value.is_number_integer() || (!value.is_number_unsigned() && value.get<std::int64_t>()<0))
    throw std::invalid_argument(std::string(key)+" must be a nonnegative integer");
  return value.get<std::uint64_t>();
}
unsigned field(const Json& j,const char* key) {
  const auto value=unsigned_json(j,key);
  if(value>std::numeric_limits<unsigned>::max()) throw std::invalid_argument(std::string(key)+" exceeds unsigned range");
  return static_cast<unsigned>(value);
}
Big hex_value(const Json& j,const char* key) {
  const auto text=j.at(key).get<std::string>();
  if(text.empty() || text.find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)
    throw std::invalid_argument(std::string(key)+" must be unsigned hex without 0x prefix");
  return Big("0x"+text);
}
}
Config config_from_json(const Json& j) {
  Config c;
  for(auto it=j.begin();it!=j.end();++it) {
    const auto& key=it.key();
    if(key=="k_fp16") c.k_fp16=field(j,key.c_str());
    else if(key=="local_shift_mag_width") c.local_shift_mag_width=field(j,key.c_str());
    else if(key=="global_signed_align_width") c.global_signed_align_width=field(j,key.c_str());
    else if(key=="post_scale_norm_extra_stage") c.post_scale_norm_extra_stage=field(j,key.c_str());
    else throw std::invalid_argument("unknown configuration key: "+key);
  }
  c.validate(); return c;
}
Request request_from_json(const Json& j) {
  Request r; r.id=unsigned_json(j,"id");
  r.a_type=static_cast<DataType>(field(j,"a_datatype"));
  r.b_type=static_cast<DataType>(field(j,"b_datatype"));
  r.c_type=static_cast<CType>(field(j,"c_datatype"));
  r.a_scale_type=static_cast<ScaleType>(field(j,"a_scale_datatype"));
  r.b_scale_type=static_cast<ScaleType>(field(j,"b_scale_datatype"));
  r.last=j.at("last").get<bool>();
  r.a=hex_value(j,"a"); r.b=hex_value(j,"b");
  auto cbits=hex_value(j,"c"); check_unsigned(cbits,int32_bits,"C payload");
  r.c=cbits.convert_to<std::uint32_t>();
  r.a_scale=hex_value(j,"a_scale"); r.b_scale=hex_value(j,"b_scale");
  r.a_e1=hex_value(j,"a_e1"); r.a_e2=hex_value(j,"a_e2");
  r.b_e1=hex_value(j,"b_e1"); r.b_e2=hex_value(j,"b_e2");
  return r;
}
Json config_json(const Config& c) {
  return {{"k_fp16",c.k_fp16},{"local_shift_mag_width",c.local_shift_mag_width},
    {"global_signed_align_width",c.global_signed_align_width},{"post_scale_norm_extra_stage",c.post_scale_norm_extra_stage},
    {"latency",c.latency()},{"groups",c.groups()},{"leaf_bits",c.leaf_bits()},
    {"lane_bits",c.lane_bits()},{"group_mag_bits",c.group_mag_bits()},{"sum_bits",c.sum_bits()}};
}
Json result_json(const Result& r) {
  std::ostringstream hex; hex<<std::hex<<std::setfill('0')<<std::setw(8)<<r.bits;
  Json j={{"id",r.id},{"d",hex.str()},{"d_datatype",static_cast<unsigned>(r.type)},{"last",r.last},
    {"flags",{{"invalid",r.flags.invalid},{"overflow",r.flags.overflow},{"underflow",r.flags.underflow},
      {"inexact",r.flags.inexact},{"integer_overflow",r.flags.integer_overflow},
      {"local_truncated",r.flags.local_truncated},{"global_truncated",r.flags.global_truncated}}}};
  if(!r.trace.empty()) j["trace"]=r.trace;
  return j;
}
Json tick_json(const Tick& t) {
  Json j={{"ready_a",t.ready},{"ready_b",t.ready},{"ready_c",t.ready},{"accepted",t.accepted},
    {"valid",t.output.has_value()},{"protocol_error",t.protocol_error}};
  if(t.output) j["result"]=result_json(*t.output);
  if(!t.registers.empty()) j["registers_after_edge"]=t.registers;
  return j;
}
} // namespace dp
