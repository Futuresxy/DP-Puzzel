#include "detail.hpp"
#include <array>
#include <stdexcept>
#include <limits>

namespace dp {
namespace {
constexpr std::array<Format,11> formats{{
  {32,8,10,127,1,ScaleType::NONE}, {16,5,10,15,2,ScaleType::NONE},
  {16,8,7,127,2,ScaleType::NONE}, {8,4,3,7,4,ScaleType::E8M0},
  {8,5,2,15,4,ScaleType::E8M0}, {8,3,2,3,4,ScaleType::E8M0},
  {8,2,3,1,4,ScaleType::E8M0}, {4,2,1,1,8,ScaleType::E8M0},
  {4,2,1,1,8,ScaleType::E4M3}, {4,0,2,0,8,ScaleType::E6M2},
  {8,0,0,0,4,ScaleType::NONE}
}};
constexpr std::array<const char*,11> names{{"tf32","fp16","bf16","mxfp8_e4m3",
  "mxfp8_e5m2","mxfp6_e3m2","mxfp6_e2m3","mxfp4_e2m1","nvfp4","hif4","int8"}};
}
const Format& format(DataType type) {
  auto i=static_cast<unsigned>(type);
  if(i>=formats.size()) throw std::invalid_argument("reserved datatype");
  return formats[i];
}
const char* name(DataType t) { (void)format(t); return names[static_cast<unsigned>(t)]; }
unsigned ceil_log2(unsigned n) {
  if(!n) throw std::invalid_argument("empty tree");
  unsigned v=0; for(--n;n;n>>=1) ++v; return v;
}
void Config::validate() const {
  if(k_fp16!=4 && k_fp16!=8 && k_fp16!=16) throw std::invalid_argument("k_fp16 must be 4,8,16");
  if(local_shift_mag_width<27) throw std::invalid_argument("local window requires F>=25");
  if(local_shift_mag_width>static_cast<unsigned>(std::numeric_limits<int>::max()/4) ||
     global_signed_align_width>static_cast<unsigned>(std::numeric_limits<int>::max()/4))
    throw std::invalid_argument("parameter exceeds software exponent/index representation");
  if(global_signed_align_width<=std::max(group_mag_bits(),int32_bits))
    throw std::invalid_argument("global magnitude window too small for input slots");
  if(post_scale_norm_extra_stage>1) throw std::invalid_argument("only L8/L9 profiles supported");
}
unsigned Config::lane_fraction(DataType t) const {
  const auto n=format(t).lane_elements;
  if(t==DataType::INT8) return lane_bits()-(int_product_bits+ceil_log2(n));
  if(n==e_elements_per_lane) {
    const unsigned natural=e_pair_bits+e_guard_bits+ceil_log2(n/2);
    const unsigned product_f=t==DataType::HIF4?4:2;
    return product_f+e_guard_bits+lane_bits()-natural;
  }
  return local_fraction()+ceil_log2(q_elements_per_lane)-ceil_log2(n);
}
bool tuple_legal(const Request& r) {
  const auto a=static_cast<unsigned>(r.a_type), b=static_cast<unsigned>(r.b_type);
  if(a>=formats.size() || a!=b) return false;
  return r.c_type==(r.a_type==DataType::INT8?CType::INT32:CType::FP32) &&
    r.a_scale_type==format(r.a_type).scale && r.b_scale_type==format(r.b_type).scale;
}
void validate_payload(const Config& c, const Request& r) {
  if(!tuple_legal(r)) throw std::invalid_argument("illegal datatype tuple");
  check_unsigned(r.a,c.packed_bits(),"packed A"); check_unsigned(r.b,c.packed_bits(),"packed B");
  check_unsigned(r.a_scale,8*c.groups(),"A scales"); check_unsigned(r.b_scale,8*c.groups(),"B scales");
  check_unsigned(r.a_e1,4*c.groups(),"A e1"); check_unsigned(r.b_e1,4*c.groups(),"B e1");
  check_unsigned(r.a_e2,2*c.groups(),"A e2"); check_unsigned(r.b_e2,2*c.groups(),"B e2");
  const auto t=r.a_type; const auto& f=format(t);
  for(const Big* data:{&r.a,&r.b}) for(unsigned i=0;i<c.elements(t);++i) {
    unsigned raw=slice(*data,i*f.storage_bits,f.storage_bits);
    if(t==DataType::TF32 && (raw&((1u<<13)-1))) throw std::invalid_argument("TF32 low13 must be zero");
    if((t==DataType::MXFP6_E3M2 || t==DataType::MXFP6_E2M3) && (raw&3))
      throw std::invalid_argument("FP6 low2 must be zero");
  }
  if(t!=DataType::HIF4 && (r.a_e1!=0 || r.a_e2!=0 || r.b_e1!=0 || r.b_e2!=0))
    throw std::invalid_argument("unused HiF metadata must be zero");
  if(f.scale==ScaleType::NONE && (r.a_scale!=0 || r.b_scale!=0))
    throw std::invalid_argument("unused scales must be zero");
  for(const Big* data:{&r.a_scale,&r.b_scale}) for(unsigned g=0;g<c.groups();++g) {
    const unsigned raw=slice(*data,g*8,8);
    if(t==DataType::NVFP4 && (raw&128)) throw std::invalid_argument("NV scale must be nonnegative");
    const unsigned first=(t==DataType::MXFP4)?(g/2)*2:0;
    if((f.scale==ScaleType::E8M0 || t==DataType::HIF4) && raw!=slice(*data,first*8,8))
      throw std::invalid_argument("scale broadcast mismatch");
  }
}
} // namespace dp
