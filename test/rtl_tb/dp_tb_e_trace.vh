// Observations only, sampled after each updating edge. E stages match E CModel.
generate for(group_index=0;group_index<G;group_index=group_index+1) begin: g_trace_group
  for(lane_index=0;lane_index<`DP_LANES;lane_index=lane_index+1) begin: g_trace_lane
    integer element_index;
    always @(negedge clock) if(trace_fd) begin
      if(dut.valid_q[0]) begin
        for(element_index=0;element_index<`DP_E_LANES;element_index=element_index+1) begin
          $fdisplay(trace_fd,"%0d 1 e_a %0d %h %0d",pending[0],
            (group_index*`DP_LANES+lane_index)*`DP_E_LANES+element_index,
            dut.g_group[group_index].group_unit.g_lane[lane_index].lane.a_mantissa_s1_q[element_index*4+:4],
            dut.g_group[group_index].group_unit.g_lane[lane_index].lane.a_sign_s1_q[element_index]);
          $fdisplay(trace_fd,"%0d 1 e_b %0d %h %0d",pending[0],
            (group_index*`DP_LANES+lane_index)*`DP_E_LANES+element_index,
            dut.g_group[group_index].group_unit.g_lane[lane_index].lane.b_mantissa_s1_q[element_index*4+:4],
            dut.g_group[group_index].group_unit.g_lane[lane_index].lane.b_sign_s1_q[element_index]);
        end
      end
      if(dut.valid_q[1]) begin
        for(element_index=0;element_index<4;element_index=element_index+1)
          $fdisplay(trace_fd,"%0d 2 e_pair %0d %0d",pending[1],
            (group_index*`DP_LANES+lane_index)*4+element_index,
            $signed(dut.g_group[group_index].group_unit.g_lane[lane_index].lane.pairs_s2_q[element_index*10+:10]));
        $fdisplay(trace_fd,"%0d 2 e_control %0d %0d %0d",pending[1],group_index*`DP_LANES+lane_index,
          dut.g_group[group_index].group_unit.g_lane[lane_index].lane.shift_s2_q,
          dut.g_group[group_index].group_unit.g_lane[lane_index].lane.all_negative_s2_q);
      end
      if(dut.valid_q[2])
        $fdisplay(trace_fd,"%0d 3 e_lane %0d %0d",pending[2],group_index*`DP_LANES+lane_index,
          $signed(dut.g_group[group_index].group_unit.g_lane[lane_index].lane.sop_s3_q));
    end
  end
  always @(negedge clock) if(trace_fd) begin
    if(dut.valid_q[3])
      $fdisplay(trace_fd,"%0d 4 e_group %0d %h %0d",pending[3],group_index,
        dut.g_group[group_index].group_unit.magnitude_s4_q,
        dut.g_group[group_index].group_unit.negative_s4_q);
    if(dut.valid_q[4])
      $fdisplay(trace_fd,"%0d 5 group %0d %h %0d %0d %0d %h",pending[4],group_index,
        dut.g_group[group_index].magnitude,$signed(dut.g_group[group_index].anchor),
        dut.g_group[group_index].leading,dut.g_group[group_index].sign_value,
        dut.g_group[group_index].special_value);
  end
end endgenerate
