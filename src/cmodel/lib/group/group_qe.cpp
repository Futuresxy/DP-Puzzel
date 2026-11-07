#include "detail.hpp"
#include <stdexcept>

namespace dp::qe_frontend {
// Reuse Q/E group arithmetic and the exact same S5 coordinate. Dedicated
// frontend width checks live at S2; S3/S4 preserve the existing RTZ boundary.
// P=LOCAL_W-2. SM output includes a separate sign, magnitude width LOCAL_W+3.
// Precision | S | I  | F
// Q         | 1 | 5  | P
// MXFP4     | 1 | 10 | P-5
// NVFP4     | 1 | 12 | P-7
// HiF4      | 1 | 10 | P-5
void stage_group(const Config &config, State &state, bool detect) {
  if (state.request.a_type < DataType::MXFP8_E4M3 || state.request.a_type > DataType::HIF4)
    throw std::invalid_argument("QE group only supports Q/E");
  dp::stage_group(config, state, detect);
}
} // namespace dp::qe_frontend
