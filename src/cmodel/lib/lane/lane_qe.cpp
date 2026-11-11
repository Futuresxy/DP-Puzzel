#include "detail.hpp"
#include <stdexcept>

namespace dp::qe_frontend {
// Q/E retain the multi frontend's S2/S3 boundary. Their S2 multiplier
// operands are unsigned W4 and results W8; no T/H reconstruction is used.
// Precision | Operand S I F | Product S I F
// Q         | 0 1 3         | 0 2 6
// MX/NV     | 0 3 1         | 0 6 2
// HiF4      | 0 2 2         | 0 4 4
void stage_products(const Config &config, State &state) {
  if (state.request.a_type < DataType::MXFP8_E4M3 || state.request.a_type > DataType::HIF4)
    throw std::invalid_argument("QE lane only supports Q/E");
  for (const auto &operand : state.operands_a) check_unsigned(operand.magnitude, 4, "QE A");
  for (const auto &operand : state.operands_b) check_unsigned(operand.magnitude, 4, "QE B");
  dp::stage_products(config, state);
  for (const auto &product : state.products) {
    check_unsigned(product.magnitude, 8, "QE product");
    check_unsigned(Big(product.exponent), 6, "QE product exponent");
  }
}
} // namespace dp::qe_frontend
