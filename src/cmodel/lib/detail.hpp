#pragma once
#include "dp/model.hpp"

namespace dp {
enum class Class { Zero, Finite, Inf, NaN };
struct Number {
  bool negative = false;
  bool signaling = false;
  Class category = Class::Zero;
  Big magnitude = 0;
  int exponent = 0; // effective biased exponent (or fixed point e2)
  unsigned fractional_bits = 0;
};
struct Special {
  bool nan = false;
  bool invalid = false;
  bool positive_inf = false;
  bool negative_inf = false;
  void merge(const Special &);
  bool active() const { return nan || invalid || positive_inf || negative_inf; }
};
struct Product {
  Big magnitude = 0;
  int exponent = 0;
  unsigned fractional_bits = 0;
  bool negative = false;
  Special special;
};
struct Token {
  Big magnitude = 0;
  int anchor_raw = 0;
  unsigned width = 0;
  unsigned fractional_bits = 0;
  unsigned leading_zero_count = 0;
  bool negative = false;
  Special special;
  bool active() const { return magnitude != 0 && !special.active(); }
};
// Only E-front-end register data. Old multi-mode intermediates are not repurposed.
struct EFrontendState {
  std::vector<std::vector<Big>> pairs;
  std::vector<unsigned> lane_shift;
  std::vector<bool> all_negative;
  std::vector<Big> scale_coefficients;
  std::vector<int> scale_exponents;
  std::vector<Big> group_magnitudes;
  std::vector<bool> group_negative;
};
struct State {
  Request request;
  // Mixed profiles retain one actual S1-S5 frontend state per physical group.
  std::vector<State> frontends;
  std::vector<bool> participate;
  bool tracing = false;
  unsigned stage = 0;
  std::vector<Number> operands_a;
  std::vector<Number> operands_b;
  std::vector<Number> scale_a;
  std::vector<Number> scale_b;
  std::vector<Product> products;
  std::vector<int> group_max_exponents;
  std::vector<Special> group_special;
  std::vector<std::vector<Big>> leaves;
  std::vector<Big> lanes;
  EFrontendState e_frontend;
  std::vector<Token> groups;
  Token c_token;
  std::vector<Big> aligned;
  Big sum = 0;
  int common = 0;
  bool negative_zero = false;
  Result result;
};
Big mask(unsigned bits);
Big abs_big(const Big &value);
unsigned bit_length(const Big &value);
unsigned clz(const Big &value, unsigned width);
void check_unsigned(const Big &, unsigned, const char *);
void check_signed(const Big &, unsigned, const char *);
Big rtz(const Big &magnitude, unsigned amount, bool &lost);
Big signed_value(const Big &magnitude, bool negative);
Big tree_sum(std::vector<Big> values, unsigned leaf_bits);
std::uint32_t round_fp32(const Big &value, int lsb_exponent, bool zero_negative, Flags &);
Number unpack_element(DataType, unsigned raw, unsigned e1, unsigned e2);
Number unpack_scale(ScaleType, unsigned raw);
Token unpack_c(CType, std::uint32_t raw);
unsigned slice(const Big &, unsigned offset, unsigned width);
Special product_special(const Number &, const Number &);
void trace(State &, const char *operation, Json data);
Json number_json(const Number &);
Json token_json(const Token &);
Json special_json(const Special &);
Json bigs_json(const std::vector<Big> &);
void stage_unpack(const Config &, State &);
void stage_products(const Config &, State &);
void stage_local_align(const Config &, State &);
void stage_lane_sum(const Config &, State &);
void stage_group(const Config &, State &, bool detect);
void detect_token(Token &);
void finish_group_stage(State &, bool detect, const Json &scale_trace);
void stage_detect(const Config &, State &);
void stage_global_align(const Config &, State &);
void stage_total(const Config &, State &);
void stage_output(const Config &, State &);
void advance(const Config &, State &, unsigned stage);
void stage_mixed_frontends(const Config &, State &, unsigned stage);
namespace qe_frontend {
void stage_products(const Config &, State &);
void stage_group(const Config &, State &, bool detect);
}
namespace e_frontend {
void stage_pairs(const Config &, State &);
void stage_lane_sum(const Config &, State &);
void stage_group_sum(const Config &, State &);
void stage_scale(const Config &, State &, bool detect);
} // namespace e_frontend
} // namespace dp
