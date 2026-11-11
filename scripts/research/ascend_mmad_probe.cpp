// Compile-only probe for the official Ascend C Basic API -> Cube ISA mapping.
// L0 inputs are intentionally uninitialized. Never execute this kernel.
// This does not validate numerical results, hardware legality, or latency.
#include "kernel_operator_mm_intf.h"

#ifndef PROBE_M
#define PROBE_M 128
#endif
#ifndef PROBE_N
#define PROBE_N 128
#endif
#ifndef PROBE_K
#define PROBE_K 128
#endif

extern "C" __global__ __aicore__ void probe_mmad() {
  AscendC::LocalTensor<half> a(AscendC::TPosition::A2, 0, PROBE_M * PROBE_K);
  AscendC::LocalTensor<half> b(AscendC::TPosition::B2, 0, PROBE_K * PROBE_N);
  AscendC::LocalTensor<float> c(AscendC::TPosition::CO1, 0, PROBE_M * PROBE_N);
  AscendC::Mmad(c, a, b,
      AscendC::MmadParams{PROBE_M, PROBE_N, PROBE_K, 0, false, true});
}
