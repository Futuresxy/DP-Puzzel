// v1.9 registered front-end cutpoints and precision-gating invariants.
genvar lane_index;
generate for (group_index=0;group_index<G;group_index=group_index+1) begin: g_v19_group
always @(negedge clock) if(trace_fd && dut.u_core.r5_valid && dut.u_core.g_group[group_index].group_top_valid)
  $fdisplay(trace_fd,"%0d 5 compare_exp %0d %0d",pending[4],group_index,
    $signed(dut.u_core.g_group[group_index].group_align_compare_exp));
`ifdef DP_LOWP_FRONTEND
for(lane_index=0;lane_index<2;lane_index=lane_index+1) begin: g_lane
  integer leaf_index;
  always @(negedge clock) if(trace_fd) begin
    if (dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r3_valid) for(leaf_index=0;leaf_index<4;leaf_index=leaf_index+1)
      $fdisplay(trace_fd,"%0d 3 frontend_leaf %0d %0d",pending[2],group_index*8+lane_index*4+leaf_index,
        $signed(dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r3_aligned_leaves[leaf_index*(LOCAL_W+1)+:LOCAL_W+1]));
    if (dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r4_valid)
      $fdisplay(trace_fd,"%0d 4 frontend_lane %0d %0d",pending[3],group_index*2+lane_index,
        $signed(dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.out_sop));
  end
  reg [8*6-1:0] previous_exponents;
  reg hold_exponents;
  always @(posedge clock) begin
    previous_exponents = dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r2_q_exponents;
    hold_exponents = ~(dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.rst_n & dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r1_valid & ~dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r1_is_e);
    #1;
    if (hold_exponents && dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r2_q_exponents !== previous_exponents) begin
      $display("FAIL v19 QE exponent gating hold"); $finish;
    end
  end
end
`else
if (group_index<4) begin: g_base
for(lane_index=0;lane_index<2;lane_index=lane_index+1) begin: g_lane
  integer leaf_index;
  always @(negedge clock) if(trace_fd) begin
    if (dut.u_core.g_group[group_index].g_base.u_group_unit.g_lane[lane_index].u_lane.r3_valid) for(leaf_index=0;leaf_index<4;leaf_index=leaf_index+1)
      $fdisplay(trace_fd,"%0d 3 frontend_leaf %0d %0d",pending[2],group_index*8+lane_index*4+leaf_index,
        $signed(dut.u_core.g_group[group_index].g_base.u_group_unit.g_lane[lane_index].u_lane.r3_aligned_leaves[leaf_index*(LOCAL_W+1)+:LOCAL_W+1]));
    if (dut.u_core.g_group[group_index].g_base.u_group_unit.g_lane[lane_index].u_lane.r4_valid)
      $fdisplay(trace_fd,"%0d 4 frontend_lane %0d %0d",pending[3],group_index*2+lane_index,
        $signed(dut.u_core.g_group[group_index].g_base.u_group_unit.g_lane[lane_index].u_lane.out_sop));
  end
end
end else begin: g_extension
`ifdef DP_Q_ONLY_EXTENSION
for(lane_index=0;lane_index<2;lane_index=lane_index+1) begin: g_lane
  integer leaf_index;
  always @(negedge clock) if(trace_fd) begin
    if (dut.u_core.g_group[group_index].g_q.u_group_unit.g_lane[lane_index].u_lane.r3_valid) for(leaf_index=0;leaf_index<4;leaf_index=leaf_index+1)
      $fdisplay(trace_fd,"%0d 3 frontend_leaf %0d %0d",pending[2],group_index*8+lane_index*4+leaf_index,
        $signed(dut.u_core.g_group[group_index].g_q.u_group_unit.g_lane[lane_index].u_lane.r3_aligned_leaves[leaf_index*(LOCAL_W+1)+:LOCAL_W+1]));
    if (dut.u_core.g_group[group_index].g_q.u_group_unit.g_lane[lane_index].u_lane.out_valid)
      $fdisplay(trace_fd,"%0d 4 frontend_lane %0d %0d",pending[3],group_index*2+lane_index,
        $signed(dut.u_core.g_group[group_index].g_q.u_group_unit.g_lane[lane_index].u_lane.out_sop));
  end
  genvar product_index;
  for(product_index=0;product_index<4;product_index=product_index+1) begin: g_q_gating
    reg [7:0] previous_product;
    reg hold_product;
    always @(posedge clock) begin
      previous_product = dut.u_core.g_group[group_index].g_q.u_group_unit.g_lane[lane_index].u_lane.r2_product[product_index];
      hold_product = ~(dut.u_core.rst_n & dut.u_core.g_group[group_index].g_q.u_group_unit.g_lane[lane_index].u_lane.r1_valid);
      #1;
      if(hold_product && dut.u_core.g_group[group_index].g_q.u_group_unit.g_lane[lane_index].u_lane.r2_product[product_index] !== previous_product) begin
        $display("FAIL Q-only product gating hold"); $finish;
      end
    end
  end
end
`elsif DP_QE_EXTENSION
for(lane_index=0;lane_index<2;lane_index=lane_index+1) begin: g_lane
  integer leaf_index;
  always @(negedge clock) if(trace_fd) begin
    if (dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r3_valid) for(leaf_index=0;leaf_index<4;leaf_index=leaf_index+1)
      $fdisplay(trace_fd,"%0d 3 frontend_leaf %0d %0d",pending[2],group_index*8+lane_index*4+leaf_index,
        $signed(dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r3_aligned_leaves[leaf_index*(LOCAL_W+1)+:LOCAL_W+1]));
    if (dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r4_valid)
      $fdisplay(trace_fd,"%0d 4 frontend_lane %0d %0d",pending[3],group_index*2+lane_index,
        $signed(dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.out_sop));
  end
  reg [8*6-1:0] previous_exponents;
  reg hold_exponents;
  always @(posedge clock) begin
    previous_exponents = dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r2_q_exponents;
    hold_exponents = ~(dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.rst_n & dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r1_valid & ~dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r1_is_e);
    #1;
    if (hold_exponents && dut.u_core.g_group[group_index].g_qe.u_group_unit.g_lane[lane_index].u_lane.r2_q_exponents !== previous_exponents) begin
      $display("FAIL v19 QE exponent gating hold"); $finish;
    end
  end
end
`else
for(lane_index=0;lane_index<2;lane_index=lane_index+1) begin: g_lane
  integer leaf_index;
  always @(negedge clock) if(trace_fd) begin
    if (dut.u_core.g_group[group_index].g_e.u_group_unit.g_lane[lane_index].u_lane.valid_q[1]) for(leaf_index=0;leaf_index<4;leaf_index=leaf_index+1)
      $fdisplay(trace_fd,"%0d 2 frontend_pair %0d %0d",pending[1],group_index*8+lane_index*4+leaf_index,
        $signed(dut.u_core.g_group[group_index].g_e.u_group_unit.g_lane[lane_index].u_lane.pairs_s2_q[leaf_index*10+:10]));
    if (dut.u_core.g_group[group_index].g_e.u_group_unit.g_lane[lane_index].u_lane.valid_q[2])
      $fdisplay(trace_fd,"%0d 3 frontend_lane %0d %0d",pending[2],group_index*2+lane_index,
        $signed(dut.u_core.g_group[group_index].g_e.u_group_unit.g_lane[lane_index].u_lane.g_v19.r3_fused_sum));
  end
end
always @(negedge clock) if(trace_fd) begin
  if (dut.u_core.g_group[group_index].g_e.u_group_unit.valid_q[3]) begin
    $fdisplay(trace_fd,"%0d 4 frontend_group_mag %0d %h %0d",pending[3],group_index,
      dut.u_core.g_group[group_index].g_e.u_group_unit.magnitude_s4_q,dut.u_core.g_group[group_index].g_e.u_group_unit.negative_s4_q);
    $fdisplay(trace_fd,"%0d 4 e_lzd22 %0d %h %0d",pending[3],group_index,
      dut.u_core.g_group[group_index].g_e.u_group_unit.g_narrow_lzd.lzd_magnitude,dut.u_core.g_group[group_index].g_e.u_group_unit.g_narrow_lzd.leading_zero_count);
  end
end
`endif
end
`endif
end endgenerate
`ifndef DP_LOWP_FRONTEND
reg [(G-4)*GLOBAL_W-1:0] previous_extension_leaves;
reg hold_extension_leaves;
always @(posedge clock) begin
  previous_extension_leaves = dut.u_core.r6_extension_leaves;
  hold_extension_leaves = ~(dut.u_core.rst_n & dut.u_core.r5_valid & dut.u_core.r5_extension);
  #1;
  if (hold_extension_leaves && dut.u_core.r6_extension_leaves !== previous_extension_leaves) begin
    $display("FAIL v19 extension leaf gating hold"); $finish;
  end
end
`endif
