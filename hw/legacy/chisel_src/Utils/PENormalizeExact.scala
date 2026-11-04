package dp.utils

import dp.config.SpecialValueFlags
import dp.utils.BalancedLeadingZero
import dp.utils.{FixedLayout, FixedPointMeta}
import chisel3._
import chisel3.util._

case class PENormalizeExactConfig(
  dataWidth: Int,
  anchorWidth: Int,
  firstStage: Int = 10
) {
  require(dataWidth >= 3, s"normalizer data width must be >=3, got $dataWidth")
  require(anchorWidth >= 3, s"normalizer anchor width must be >=3, got $anchorWidth")
  val normalizedLayout: FixedLayout = FixedPointMeta.topAnchoredLayout(dataWidth)
  require(
    normalizedLayout == FixedLayout(1, 1, dataWidth - 2),
    s"MidGroup LZD output must be W$dataWidth S-I-F=1-1-${dataWidth - 2}"
  )
}

class PENormalizeExactInput(cfg: PENormalizeExactConfig) extends Bundle {
  val result = SInt(cfg.dataWidth.W)
  val raw_top_anchor = SInt(cfg.anchorWidth.W)
  val special = new SpecialValueFlags
}

class PENormalizeExactOutput(cfg: PENormalizeExactConfig) extends Bundle {
  val magnitude = UInt((cfg.dataWidth - 1).W)
  val negative = Bool()
  val normalized_top_anchor = SInt(cfg.anchorWidth.W)
  val is_zero = Bool()
  val special = new SpecialValueFlags
}

/**
  * Two-stage, forward-only lossless signed fixed-point normalizer.
  *
  * For a W-bit carrier `(R,A)`, A is the exponent of bit W-2:
  *
  *   Value = R * 2^(A-(W-2)).
  *
  * S10 forms a W+1-bit-safe magnitude and counts leading zeros. S11 places the
  * leading magnitude one at bit W-2 and adjusts A by the opposite amount. No
  * result bit is rounded, truncated, or compressed.
  */
class PENormalizeExact(cfg: PENormalizeExactConfig) extends Module {
  private val dataWidth = cfg.dataWidth
  private val anchorWidth = cfg.anchorWidth
  private val lzcWidth = math.max(1, log2Ceil(dataWidth + 1))
  private val zero_anchor = (-(BigInt(1) << (anchorWidth - 1))).S(anchorWidth.W)

  val io = IO(new Bundle {
    val in_data = Flipped(Valid(new PENormalizeExactInput(cfg)))
    val out_data = Valid(new PENormalizeExactOutput(cfg))
  })

  // -------------------------------------------------------------------------
  // S10: W+1-safe abs, zero detection, and leading-zero count over W magnitude
  // positions. LZC=0 is reserved for the representable minimum SInt only.
  // -------------------------------------------------------------------------
  val input_wide = io.in_data.bits.result.pad(dataWidth + 1)
  val input_negative = input_wide < 0.S
  val input_magnitude_wide = Mux(
    input_negative,
    (-input_wide).asUInt,
    input_wide.asUInt
  )
  val input_magnitude = input_magnitude_wide(dataWidth - 1, 0)
  val input_zero = input_magnitude === 0.U
  val input_lzc = BalancedLeadingZero.count(input_magnitude)

  val s10_valid_q = RegNext(io.in_data.valid, false.B).suggestName(f"s${cfg.firstStage}%02d_valid_q")
  val s10_magnitude_q = Reg(UInt(dataWidth.W)).suggestName(f"s${cfg.firstStage}%02d_magnitude_q")
  val s10_negative_q = Reg(Bool()).suggestName(f"s${cfg.firstStage}%02d_negative_q")
  val s10_zero_q = Reg(Bool()).suggestName(f"s${cfg.firstStage}%02d_zero_q")
  val s10_lzc_q = Reg(UInt(lzcWidth.W)).suggestName(f"s${cfg.firstStage}%02d_lzc_q")
  val s10_raw_top_anchor_q = Reg(SInt(anchorWidth.W)).suggestName(f"s${cfg.firstStage}%02d_raw_top_anchor_q")
  val s10_special_q = Reg(new SpecialValueFlags).suggestName(f"s${cfg.firstStage}%02d_special_q")

  val s11_valid_q = RegNext(s10_valid_q, false.B).suggestName(f"s${cfg.firstStage + 1}%02d_valid_q")
  val s11_bits_q = Reg(new PENormalizeExactOutput(cfg)).suggestName(f"s${cfg.firstStage + 1}%02d_bits_q")
  when(io.in_data.valid) {
    locally {
      assert(!input_magnitude_wide(dataWidth),
        "W+1 magnitude overflow is impossible for a W-bit signed input")
      s10_magnitude_q := input_magnitude
      s10_negative_q := input_negative
      s10_zero_q := input_zero
      s10_lzc_q := input_lzc
      s10_raw_top_anchor_q := io.in_data.bits.raw_top_anchor
      s10_special_q := io.in_data.bits.special
    }
  }

  // -------------------------------------------------------------------------
  // S11: exact normalization and corrected-anchor calculation.
  // Ordinary values have LZC>=1 and shift left by LZC-1. The minimum negative
  // value has LZC=0; shift its magnitude right once and increase the anchor.
  // Both cases obey A_norm = A_raw + 1 - LZC.
  // -------------------------------------------------------------------------
  val min_negative_case = !s10_zero_q && s10_lzc_q === 0.U
  val left_amount = Mux(s10_lzc_q === 0.U, 0.U, s10_lzc_q - 1.U)
  val shifted_magnitude = s10_magnitude_q << left_amount
  val ordinary_magnitude = shifted_magnitude(dataWidth - 2, 0)
  val min_negative_magnitude = s10_magnitude_q(dataWidth - 1, 1)
  val normalized_magnitude = Mux(
    min_negative_case,
    min_negative_magnitude,
    ordinary_magnitude
  )

  val corrected_anchor_wide = s10_raw_top_anchor_q.pad(anchorWidth + 2) +
    1.S((anchorWidth + 2).W) - s10_lzc_q.zext.pad(anchorWidth + 2)
  val corrected_anchor = Wire(SInt(anchorWidth.W))
  corrected_anchor := corrected_anchor_wide.asUInt(anchorWidth - 1, 0).asSInt
  when(s10_valid_q && !s10_zero_q) {
    assert(
      corrected_anchor_wide === corrected_anchor.pad(anchorWidth + 2),
      "normalized top-anchor overflow"
    )
  }

  when(s10_valid_q) {
    locally {
      when(min_negative_case) {
        assert(s10_magnitude_q === (BigInt(1) << (dataWidth - 1)).U,
          "LZC=0 must identify only the minimum signed value")
      }
      when(!s10_zero_q) {
        assert(normalized_magnitude(dataWidth - 2),
          "nonzero normalized magnitude must have its leading one at W-2")
      }
      // The next consumer aligns magnitudes. Keep the sign separate instead of
      // negating here only to take another absolute value before that shift.
      s11_bits_q.magnitude := Mux(s10_zero_q, 0.U, normalized_magnitude)
      s11_bits_q.negative := !s10_zero_q && s10_negative_q
      s11_bits_q.normalized_top_anchor := Mux(s10_zero_q, zero_anchor, corrected_anchor)
      s11_bits_q.is_zero := s10_zero_q
      s11_bits_q.special := s10_special_q
    }
  }

  io.out_data.valid := s11_valid_q
  io.out_data.bits := s11_bits_q
}


/* Output W/S/I/F: every caller format uses W=cfg.dataWidth, S=1, I=1,
 * F=W-2 (default W42/S1/I1/F40). Sign and W-1 magnitude travel separately;
 * value = (-1)^negative * magnitude * 2^(normalizedTopAnchor-(W-2)).
 * firstStage labels abs/LZD; firstStage+1 labels the normalized output register.
 */
