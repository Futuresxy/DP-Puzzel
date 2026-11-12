#include "detail.hpp"
#include <stdexcept>

namespace dp::q_frontend {
// Q-only reuses the audited four-product numerical path; no E modes are legal.
// Operand U4/F3, product U8/F6, unchanged Q alignment and S5 coordinate.
void stage_group(const Config &config, State &state, bool detect) {
  if (state.request.a_type < DataType::MXFP8_E4M3 || state.request.a_type > DataType::MXFP6_E2M3)
    throw std::invalid_argument("Q group only supports MXFP8/6");
  dp::stage_group(config, state, detect);
}
} // namespace dp::q_frontend
