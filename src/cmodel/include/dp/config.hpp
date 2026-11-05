#pragma once
#include <cstddef>
#include <string>

namespace dp {
enum class DataType { TF32, FP16, BF16, MXFP8_E4M3, MXFP8_E5M2,
  MXFP6_E3M2, MXFP6_E2M3, MXFP4, NVFP4, HIF4, INT8 };
enum class CType { FP32, INT32 };
enum class ScaleType { NONE, E8M0, E4M3, E6M2 };
enum class Frontend { Multi, E };

// Format/architecture constants are named here; adjustable windows are Config fields.
struct Format {
  unsigned storage_bits, exponent_bits, fraction_bits, bias, lane_elements;
  ScaleType scale;
};
const Format& format(DataType type);
const char* name(DataType type);
constexpr unsigned lanes_per_group = 2;
constexpr unsigned q_elements_per_lane = 4;
constexpr unsigned e_elements_per_lane = 8;
constexpr unsigned fp16_per_group = 4;
constexpr unsigned e_guard_bits = 2;
constexpr unsigned e_pair_bits = 10;
constexpr unsigned int_product_bits = 16;
constexpr unsigned scale_fraction_bits = 3;
constexpr unsigned scale_bias = 127;
constexpr unsigned fp32_fraction_bits = 23;
constexpr unsigned fp32_magnitude_bits = 24;
constexpr unsigned int32_bits = 32;
constexpr unsigned base_latency = 8;
constexpr unsigned mul_hi_bits = 8, mul_lo_bits = 4;
constexpr unsigned mul_groups_per_lane = 2;
constexpr unsigned scale_magnitude_bits = 4;
constexpr unsigned e_compact_group_bits = e_pair_bits + e_guard_bits + 2 + 1;
constexpr unsigned e_pairs_per_lane = e_elements_per_lane / 2;
constexpr unsigned e_lane_raw_bits = e_pair_bits + 2;
constexpr unsigned e_lane_fused_bits = e_lane_raw_bits + e_guard_bits;
constexpr unsigned e_group_fraction_bits = 4;
constexpr unsigned canonical_nan = 0x7fc00000u;
unsigned ceil_log2(unsigned n);

struct Config {
  // Build-time knobs shared with RTL. Container widths/tree growth below
  // are derived, never additional independently adjustable precisions.
  unsigned k_fp16 = 16;
  unsigned local_shift_mag_width = 28;
  unsigned global_signed_align_width = 40;
  unsigned post_scale_norm_extra_stage = 0;
  Frontend frontend = Frontend::Multi;
  void validate() const;
  unsigned groups() const { return k_fp16 / fp16_per_group; }
  unsigned lanes() const { return groups() * lanes_per_group; }
  unsigned elements(DataType t) const { return lanes() * format(t).lane_elements; }
  unsigned packed_bits() const { return k_fp16 * 16; }
  unsigned local_fraction() const { return local_shift_mag_width - 2; } // S0I2F(local-2)
  unsigned leaf_bits() const { return frontend==Frontend::E?e_pair_bits:local_shift_mag_width+1; }
  unsigned lane_bits() const { return frontend==Frontend::E?e_lane_raw_bits:leaf_bits()+ceil_log2(q_elements_per_lane); }
  unsigned group_bits() const { return frontend==Frontend::E?e_compact_group_bits:group_mag_bits()+1; }
  // S5's exported magnitude slot stays compatible across frontend types.
  unsigned group_mag_bits() const { return local_shift_mag_width+ceil_log2(q_elements_per_lane)+ceil_log2(lanes_per_group); }
  unsigned global_mag_bits() const { return global_signed_align_width - 1; }
  unsigned sum_bits() const { return global_signed_align_width + ceil_log2(groups()+1); }
  unsigned latency() const { return base_latency + post_scale_norm_extra_stage; }
  unsigned lane_fraction(DataType type) const;
};
} // namespace dp
