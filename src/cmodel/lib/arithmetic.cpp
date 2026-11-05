#include "detail.hpp"
#include <stdexcept>

namespace dp {
Big mask(unsigned bits) { return (Big(1)<<bits)-1; }
Big abs_big(const Big& x) { return x<0?Big(-x):x; }
unsigned bit_length(const Big& x) { return x==0?0:boost::multiprecision::msb(x)+1; }
unsigned clz(const Big& x,unsigned width) {
  check_unsigned(x,width,"LZD input");
  return x==0?0:width-bit_length(x); // zero is separately masked, never a numeric exponent
}
void check_unsigned(const Big& x,unsigned w,const char* what) {
  if(x<0 || x>(mask(w))) throw std::invalid_argument(std::string(what)+": unsigned width overflow");
}
void check_signed(const Big& x,unsigned w,const char* what) {
  if(!w || x<-(Big(1)<<(w-1)) || x>=(Big(1)<<(w-1)))
    throw std::logic_error(std::string(what)+": signed width overflow");
}
Big rtz(const Big& x,unsigned amount,bool& lost) {
  if(x<0) throw std::logic_error("RTZ requires magnitude");
  if(amount>=bit_length(x)) { lost|=(x!=0); return 0; }
  Big y=x>>amount; lost|=((y<<amount)!=x); return y;
}
Big signed_value(const Big& mag,bool negative) { return negative?Big(-mag):mag; }
unsigned slice(const Big& x,unsigned offset,unsigned width) { return ((x>>offset)&mask(width)).convert_to<unsigned>(); }
// TC inputs S1I(i)F(f) -> S1I(i+ceil(log2(N)))F(f).
Big tree_sum(std::vector<Big> values,unsigned width) {
  if(values.empty()) throw std::logic_error("empty sum tree");
  for(const auto& x:values) check_signed(x,width,"tree leaf");
  while(values.size()>1) {
    std::vector<Big> next;
    for(std::size_t i=0;i<values.size();i+=2) {
      Big s=values[i]; if(i+1<values.size()) s+=values[i+1];
      check_signed(s,width+1,"tree node"); next.push_back(s);
    }
    values=std::move(next); ++width;
  }
  return values.front();
}
namespace {
Big round_even(const Big& m,int shift,bool& inexact) {
  if(shift<=0) return m<<(-shift);
  Big q=m>>shift, rem=m-(q<<shift), half=Big(1)<<(shift-1);
  inexact|=rem!=0;
  if(rem>half || (rem==half && static_cast<bool>(q&1))) ++q;
  return q;
}
}
// TC coefficient at the supplied LSB exponent -> FP32 S1/E8/F23.
std::uint32_t round_fp32(const Big& value,int lsb,bool negative_zero,Flags& flags) {
  const bool negative=value<0 || (value==0 && negative_zero);
  const std::uint32_t sign=negative?0x80000000u:0;
  const Big m=abs_big(value);
  if(m==0) return sign;
  int e=lsb+static_cast<int>(bit_length(m))-1;
  if(e>=-126) {
    Big significand=round_even(m,static_cast<int>(bit_length(m))-static_cast<int>(fp32_magnitude_bits),flags.inexact);
    if(significand==(Big(1)<<fp32_magnitude_bits)) { significand>>=1; ++e; }
    if(e>127) { flags.overflow=true; flags.inexact=true; return sign|0x7f800000u; }
    return sign|(static_cast<std::uint32_t>(e+127)<<fp32_fraction_bits)|
      (significand&mask(fp32_fraction_bits)).convert_to<std::uint32_t>();
  }
  Big fraction=round_even(m,-149-lsb,flags.inexact);
  flags.underflow=flags.inexact && fraction<(Big(1)<<fp32_fraction_bits);
  // Rounding a largest subnormal upward naturally sets exponent bit zero to one.
  return sign|fraction.convert_to<std::uint32_t>();
}
void Special::merge(const Special& o) {
  nan|=o.nan; invalid|=o.invalid; positive_inf|=o.positive_inf; negative_inf|=o.negative_inf;
  invalid|=positive_inf&&negative_inf;
}
Special product_special(const Number& a,const Number& b) {
  Special s; s.nan=a.category==Class::NaN || b.category==Class::NaN;
  s.invalid=a.signaling || b.signaling;
  bool inf=a.category==Class::Inf || b.category==Class::Inf;
  bool zero=a.category==Class::Zero || b.category==Class::Zero;
  s.invalid|=inf&&zero;
  if(inf && !zero && !s.nan) {
    if(a.negative!=b.negative) s.negative_inf=true; else s.positive_inf=true;
  }
  return s;
}
void trace(State& s,const char* operation,Json data) {
  if(s.tracing) s.result.trace.push_back({{"stage",s.stage},{"operation",operation},{"data",std::move(data)}});
}
Json special_json(const Special& x) { return {{"nan",x.nan},{"invalid",x.invalid},{"positive_inf",x.positive_inf},{"negative_inf",x.negative_inf}}; }
Json number_json(const Number& n) { return {{"sign",n.negative},{"m",n.magnitude.str()},{"e",n.exponent},{"f",n.fraction},{"class",static_cast<int>(n.category)},{"signaling",n.signaling}}; }
Json token_json(const Token& t) { return {{"sign",t.negative},{"m",t.magnitude.str()},{"width",t.width},{"f",t.fraction},{"anchor_raw",t.anchor_raw},{"z",t.z},{"e",t.anchor_raw-static_cast<int>(t.z)},{"zero",t.magnitude==0},{"special",special_json(t.special)}}; }
Json bigs_json(const std::vector<Big>& values) { Json a=Json::array(); for(const auto& x:values) a.push_back(x.str()); return a; }
} // namespace dp
