#pragma once
#include "dp/model.hpp"

namespace dp {
enum class Class { Zero, Finite, Inf, NaN };
struct Number {
  bool negative = false, signaling = false;
  Class category = Class::Zero;
  Big magnitude = 0;
  int exponent = 0; // effective biased exponent (or fixed point e2)
  unsigned fraction = 0;
};
struct Special {
  bool nan = false, invalid = false, positive_inf = false, negative_inf = false;
  void merge(const Special&);
  bool active() const { return nan || invalid || positive_inf || negative_inf; }
};
struct Product {
  Big magnitude = 0;
  int exponent = 0;
  unsigned fraction = 0;
  bool negative = false;
  Special special;
};
struct Token {
  Big magnitude = 0;
  int anchor_raw = 0;
  unsigned width = 0, fraction = 0, z = 0;
  bool negative = false;
  Special special;
  bool active() const { return magnitude != 0 && !special.active(); }
};
struct State {
  Request request;
  bool tracing = false;
  unsigned stage = 0;
  std::vector<Number> a, b, scale_a, scale_b;
  std::vector<Product> products;
  std::vector<int> r;
  std::vector<Special> group_special;
  std::vector<std::vector<Big>> leaves;
  std::vector<Big> lanes;
  std::vector<Token> groups;
  Token c;
  std::vector<Big> aligned;
  Big sum = 0;
  int common = 0;
  bool negative_zero = false;
  Result result;
};
Big mask(unsigned bits);
Big abs_big(const Big& x);
unsigned bit_length(const Big& x);
unsigned clz(const Big& x, unsigned width);
void check_unsigned(const Big&, unsigned, const char*);
void check_signed(const Big&, unsigned, const char*);
Big rtz(const Big& magnitude, unsigned amount, bool& lost);
Big signed_value(const Big& mag, bool negative);
Big tree_sum(std::vector<Big> values, unsigned leaf_bits);
std::uint32_t round_fp32(const Big& value, int lsb_exponent, bool zero_negative, Flags&);
Number unpack_element(DataType, unsigned raw, unsigned e1, unsigned e2);
Number unpack_scale(ScaleType, unsigned raw);
Token unpack_c(CType, std::uint32_t raw);
unsigned slice(const Big&, unsigned offset, unsigned width);
Special product_special(const Number&, const Number&);
void trace(State&, const char* operation, Json data);
Json number_json(const Number&);
Json token_json(const Token&);
Json special_json(const Special&);
Json bigs_json(const std::vector<Big>&);
void stage_unpack(const Config&, State&);
void stage_products(const Config&, State&);
void stage_local_align(const Config&, State&);
void stage_lane_sum(const Config&, State&);
void stage_group(const Config&, State&, bool detect);
void stage_detect(const Config&, State&);
void stage_global_align(const Config&, State&);
void stage_total(const Config&, State&);
void stage_output(const Config&, State&);
void advance(const Config&, State&, unsigned stage);
} // namespace dp
