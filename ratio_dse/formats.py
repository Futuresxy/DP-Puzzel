"""Operand layouts at the declared local input boundary."""

from .common import ceil_div, integer

# Native capacity keys follow the verified DP implementations. For MXFP6
# use byte slots, as in the current DP input contract.
FORMATS = {
    "tf32": ("t", 32, None, None),
    "fp16": ("h", 16, None, None),
    "bf16": ("h", 16, None, None),
    "mxfp8_e4m3": ("q", 8, 32, "e8m0"),
    "mxfp8_e5m2": ("q", 8, 32, "e8m0"),
    "mxfp6_e3m2": ("q", 8, 32, "e8m0"),
    "mxfp6_e2m3": ("q", 8, 32, "e8m0"),
    "mxfp4_e2m1": ("e", 4, 32, "e8m0"),
    "nvfp4": ("e", 4, 16, "e4m3"),
    "hif4": ("e", 4, 64, "e6m2"),
    "int8": ("int8", 8, None, None),
}


def layout(format_id):
    _, bits, block, scale_format = FORMATS[format_id]
    return {"element_slot_bits": bits, "scale_block_elements": block, "scale_format": scale_format,
            "scale_bits": 8 if block else 0, "auxiliary_bit_periods": [4, 8] if format_id == "hif4" else []}


def vector_bytes(elements, spec):
    """Independent byte-aligned payload and metadata streams for one vector."""
    payload = ceil_div(elements * integer("element_slot_bits", spec["element_slot_bits"]), 8)
    scale = 0
    block = spec.get("scale_block_elements")
    if block is not None:
        scale = ceil_div(ceil_div(elements, integer("scale block", block))
                         * integer("scale_bits", spec["scale_bits"]), 8)
    auxiliary = sum(ceil_div(ceil_div(elements, integer("auxiliary period", period)), 8)
                    for period in spec.get("auxiliary_bit_periods", []))
    return payload, scale + auxiliary
