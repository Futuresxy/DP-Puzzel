"""Software format checks; these do not qualify the RTL numerical design."""
import math
import struct
import unittest

from formats import FORMATS, decode, decode_scale, dequantize, encode, quantize_rows
from golden import k_indices
from quantize import packed_words


class FormatTests(unittest.TestCase):
    def test_ieee_half_and_bfloat_decoders(self):
        for raw in range(65536):
            for name, reference in (("fp16", struct.unpack("<e", struct.pack("<H", raw))[0]),
                                    ("bf16", struct.unpack("<f", struct.pack("<I", raw << 16))[0])):
                got = decode(name, raw)
                if math.isnan(reference):
                    self.assertTrue(math.isnan(got))
                else:
                    self.assertEqual(got, reference)
                    if reference == 0:
                        self.assertEqual(math.copysign(1, got), math.copysign(1, reference))

    def test_low_precision_known_encodings(self):
        self.assertEqual([decode("mxfp4", i) for i in range(8)], [0, .5, 1, 1.5, 2, 3, 4, 6])
        self.assertEqual([decode("hif4", i) for i in range(8)], [i / 4 for i in range(8)])
        self.assertEqual(decode("mxfp6_e3m2", 31), 28)
        self.assertEqual(decode("mxfp6_e2m3", 31), 7.5)
        self.assertEqual(decode("mxfp8_e4m3", 126), 448)
        self.assertTrue(math.isnan(decode("mxfp8_e4m3", 127)))
        self.assertEqual(decode("mxfp8_e5m2", 124), math.inf)

    def test_finite_roundtrips_and_ties(self):
        for name, f in FORMATS.items():
            for raw in range(1 << f.bits):
                value = decode(name, raw)
                if math.isfinite(value):
                    self.assertEqual(encode(name, value), raw)
        self.assertEqual(encode("mxfp4", .25), 0)
        self.assertEqual(encode("mxfp4", .75), 2)
        self.assertEqual(encode("hif4", .125), 0)
        self.assertEqual(encode("hif4", .375), 2)
        self.assertEqual(encode("fp16", 1e30), 0x7bff)

    def test_scale_definitions(self):
        self.assertEqual(decode_scale("e8m0", 0), 2 ** -127)
        self.assertEqual(decode_scale("e8m0", 254), 2 ** 127)
        self.assertTrue(math.isnan(decode_scale("e8m0", 255)))
        self.assertEqual(decode_scale("e6m2", 0), 2 ** -48)
        self.assertEqual(decode_scale("e6m2", 254), 1.5 * 2 ** 15)
        self.assertEqual(decode_scale("e6m2", 192), 1)

    def test_quantized_blocks_and_storage(self):
        import numpy as np
        source = np.array([[0, 1, -1, 2] * 16], dtype=np.float64)
        for name in FORMATS:
            q = quantize_rows(source, name)
            values = dequantize(q["codes"], name, q["scales"], q["g0"], q["g1"])
            self.assertTrue(np.isfinite(values).all())
            words = packed_words(q["codes"], name)
            if FORMATS[name].bits == 6:
                self.assertTrue(np.all((words & 0xc0c0) == 0))
        zero = quantize_rows(np.zeros((1, 64)), "hif4")
        self.assertEqual(int(zero["scales"][0, 0]), 0xc0)
        self.assertFalse(zero["g0"].any() or zero["g1"].any() or zero["codes"].any())

    def test_hif4_k96_mapping(self):
        chunks = k_indices("hif4", 96, 768)
        self.assertEqual(sorted(index for row in chunks for index in row), list(range(768)))
        self.assertEqual(chunks[1], list(range(128, 192)) + list(range(96, 128)))
        for chunk in chunks:
            self.assertEqual(len({i // 64 for i in chunk[:64]}), 1)
            self.assertEqual(len({i // 64 for i in chunk[64:]}), 1)


if __name__ == "__main__":
    unittest.main()
