#include "detail.hpp"
#include <array>

namespace dp {
namespace {
Number binary(unsigned raw,unsigned ebits,unsigned fbits,unsigned bias,
              bool ieee_special,bool finite_e4m3) {
  Number n; n.negative=(raw>>(ebits+fbits))&1;
  const unsigned e=(raw>>fbits)&((1u<<ebits)-1), f=raw&((1u<<fbits)-1);
  n.fraction=fbits; n.exponent=e?static_cast<int>(e):1;
  const bool special=e==((1u<<ebits)-1);
  if((ieee_special&&special&&f) || (finite_e4m3&&special&&f==((1u<<fbits)-1))) {
    n.category=Class::NaN; n.signaling=ieee_special && !(f&(1u<<(fbits-1)));
    n.exponent=1; return n;
  }
  if(ieee_special&&special&&!f) { n.category=Class::Inf; n.exponent=1; return n; }
  n.magnitude=(e?(1u<<fbits):0)|f;
  n.category=n.magnitude==0?Class::Zero:Class::Finite;
  (void)bias; return n;
}
Json layout(const std::vector<Number>& values,DataType type) {
  Json atoms=Json::array(); const auto& f=format(type);
  const unsigned per_atom=type==DataType::TF32?1:f.lane_elements/2;
  for(unsigned i=0;i<values.size();i+=per_atom) {
    unsigned e=0,m=0,s=0;
    for(unsigned j=0;j<per_atom;++j) {
      const auto& n=values[i+j]; unsigned mant=n.magnitude.convert_to<unsigned>();
      if(type==DataType::INT8) m|=mant<<(8*j);
      else if(f.lane_elements>=4) m|=mant<<(4*j);
      else m=mant;
      s|=unsigned(n.negative)<<j;
      if(type==DataType::HIF4) e=static_cast<unsigned>(n.exponent);
      else if(f.lane_elements==4 && type!=DataType::INT8) e|=static_cast<unsigned>(n.exponent)<<(5*j);
      else if(f.lane_elements<4) e=static_cast<unsigned>(n.exponent);
    }
    atoms.push_back({{"E",e},{"M",m},{"S",s}});
  }
  return atoms;
}
}
// Logical SM: TF32/FP16 S1I1F10, BF16 S1I1F7, MXFP8/6 S1I1F3,
// MXFP4/NVFP4 S1I3F1, HiF4 S1I2F2, INT8 S1I8F0. Exponent is separate.
Number unpack_element(DataType type,unsigned raw,unsigned e1,unsigned e2) {
  const auto& f=format(type); Number n;
  if(type==DataType::INT8) {
    n.negative=(raw&128)!=0; n.magnitude=n.negative?256-raw:raw;
  } else if(type==DataType::HIF4) {
    n.negative=(raw&8)!=0; n.magnitude=(raw&7)<<e1; n.exponent=e2; n.fraction=2;
  } else if(type==DataType::MXFP4 || type==DataType::NVFP4) {
    constexpr std::array<unsigned,8> coeff{{0,1,2,3,4,6,8,12}};
    n.negative=(raw&8)!=0; n.magnitude=coeff[raw&7]; n.fraction=1;
  } else {
    if(type==DataType::TF32) raw>>=13;
    if(type==DataType::MXFP6_E3M2 || type==DataType::MXFP6_E2M3) raw>>=2;
    const bool ieee=type==DataType::TF32 || type==DataType::FP16 || type==DataType::BF16 || type==DataType::MXFP8_E5M2;
    n=binary(raw,f.exponent_bits,f.fraction_bits,f.bias,ieee,type==DataType::MXFP8_E4M3);
    if(f.lane_elements==q_elements_per_lane) {
      if(n.category!=Class::NaN && n.category!=Class::Inf) n.exponent+=15-static_cast<int>(f.bias);
      n.magnitude<<=scale_fraction_bits-f.fraction_bits; n.fraction=scale_fraction_bits;
    }
    return n;
  }
  n.category=n.magnitude==0?Class::Zero:Class::Finite; return n;
}
// E8M0/E4M3/E6M2 and unit scale use S0I1F3 plus a biased exponent.
Number unpack_scale(ScaleType type,unsigned raw) {
  Number n; n.exponent=scale_bias; n.fraction=scale_fraction_bits;
  if(type==ScaleType::NONE) n.magnitude=1u<<scale_fraction_bits;
  else if(type==ScaleType::E8M0) {
    if(raw==255) { n.category=Class::NaN; return n; }
    n.exponent=raw; n.magnitude=1u<<scale_fraction_bits;
  } else if(type==ScaleType::E6M2) {
    if(raw==255) { n.category=Class::NaN; return n; }
    n.exponent=static_cast<int>(raw>>2)+127-48;
    n.magnitude=(4+(raw&3))<<1;
  } else {
    n=binary(raw,4,3,7,false,true);
    if(n.category!=Class::NaN) n.exponent+=127-7;
  }
  if(n.category!=Class::NaN) n.category=n.magnitude==0?Class::Zero:Class::Finite;
  return n;
}
// S5 SM output: FP32 S1I1F31 (S0I1F23 padded by 8 zeros), INT32 S1I32F0.
Token unpack_c(CType type,std::uint32_t raw) {
  Token t; t.width=int32_bits;
  if(type==CType::INT32) {
    Big value=raw; if(raw&0x80000000u) value-=Big(1)<<int32_bits;
    t.negative=value<0; t.magnitude=abs_big(value); return t;
  }
  const auto n=binary(raw,8,fp32_fraction_bits,127,true,false);
  t.negative=n.negative; t.magnitude=n.magnitude<<(int32_bits-fp32_magnitude_bits);
  t.fraction=int32_bits-1; t.anchor_raw=n.exponent-127;
  t.special.nan=n.category==Class::NaN; t.special.invalid=n.signaling;
  if(n.category==Class::Inf) {
    t.special.positive_inf=!n.negative; t.special.negative_inf=n.negative;
  }
  return t;
}
void stage_unpack(const Config& c,State& s) {
  const auto& r=s.request; const auto& f=format(r.a_type);
  for(unsigned i=0;i<c.elements(r.a_type);++i) {
    auto one=[&](const Big& data,const Big& e1,const Big& e2) {
      return unpack_element(r.a_type,slice(data,i*f.storage_bits,f.storage_bits),slice(e1,i/4,1),slice(e2,i/8,1));
    };
    s.a.push_back(one(r.a,r.a_e1,r.a_e2)); s.b.push_back(one(r.b,r.b_e1,r.b_e2));
  }
  for(unsigned g=0;g<c.groups();++g) {
    s.scale_a.push_back(unpack_scale(r.a_scale_type,slice(r.a_scale,g*8,8)));
    s.scale_b.push_back(unpack_scale(r.b_scale_type,slice(r.b_scale,g*8,8)));
  }
  if(s.tracing) {
    Json aa=Json::array(),bb=aa,sa=aa,sb=aa;
    for(const auto& n:s.a) aa.push_back(number_json(n));
    for(const auto& n:s.b) bb.push_back(number_json(n));
    for(const auto& n:s.scale_a) sa.push_back(number_json(n));
    for(const auto& n:s.scale_b) sb.push_back(number_json(n));
    trace(s,"unpack",{{"a",aa},{"b",bb},{"a_layout",layout(s.a,r.a_type)},{"b_layout",layout(s.b,r.b_type)},
      {"scale_a",sa},{"scale_b",sb},{"c_raw",r.c}});
  }
}
} // namespace dp
