#include "detail.hpp"
#include <stdexcept>

namespace dp::q_frontend {
// Q-only reuses the audited four-product numerical path; no E modes are legal.
// Operand U4/F3, product U8/F6, unchanged Q alignment and S5 coordinate.
void stage_products(const Config &config, State &state) {
  if (state.request.a_type < DataType::MXFP8_E4M3 || state.request.a_type > DataType::MXFP6_E2M3)
    throw std::invalid_argument("Q lane only supports MXFP8/6");
  for (const auto &operand : state.operands_a) check_unsigned(operand.magnitude, 4, "QE A");
  for (const auto &operand : state.operands_b) check_unsigned(operand.magnitude, 4, "QE B");
  dp::stage_products(config, state);
  for (const auto &product : state.products) {
    check_unsigned(product.magnitude, 8, "QE product");
    check_unsigned(Big(product.exponent), 6, "QE product exponent");
  }
}
} // namespace dp::q_frontend
