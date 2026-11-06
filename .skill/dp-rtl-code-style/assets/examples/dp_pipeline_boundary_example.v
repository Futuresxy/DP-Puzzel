// Structural example only, not an implementation of the DP S3 arithmetic.
// Store an opaque magnitude and its separate sign at the S2 -> S3 boundary.
// Magnitude S=0, I+F=DATA_W; the caller defines the binary-point coordinate.
// One edge of latency, II=1, no backpressure; reset cancels valid synchronously.
module dp_pipeline_boundary_example #(
  parameter integer DATA_W = 28
) (
  input wire clock,
  input wire rst_n,
  input wire in_valid,
  input wire [DATA_W-1:0] in_magnitude,
  input wire in_sign,
  output wire out_valid,
  output wire [DATA_W-1:0] out_magnitude,
  output wire out_sign
);

  localparam integer SIGN_W = 1;
  localparam integer PAYLOAD_W = SIGN_W + DATA_W;

  wire valid_s3_d;
  wire valid_s3_q;
  wire payload_s3_en;
  wire [PAYLOAD_W-1:0] payload_s3_d;
  wire [PAYLOAD_W-1:0] payload_s3_q;
  wire [DATA_W-1:0] magnitude_s3_q;
  wire sign_s3_q;

  assign valid_s3_d = in_valid;
  assign payload_s3_en = rst_n & in_valid;
  assign payload_s3_d = {in_sign, in_magnitude};

  // S2 -> S3 control: advance every edge, including bubbles; reset to invalid.
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_s3_d), .out_q(valid_s3_q));

  // S2 -> S3 payload: save only a valid item, hold during reset and bubbles.
  dp_lib_DFFE #(.WIDTH(PAYLOAD_W))
  ff_s2_s3_payload (.clock(clock), .in_en(payload_s3_en), .in_d(payload_s3_d), .out_q(payload_s3_q));
  // verilog_format: on
  assign {sign_s3_q, magnitude_s3_q} = payload_s3_q;

  assign out_valid = valid_s3_q;
  assign out_magnitude = magnitude_s3_q;
  assign out_sign = sign_s3_q;

endmodule
