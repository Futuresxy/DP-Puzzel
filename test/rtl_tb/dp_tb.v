`include "dp_defs.vh"
`timescale 1ns/1ps
// Shared DP_INPUTS_V1 reader and pre-edge, fixed-latency scoreboard.
// Stimulus sidecar controls reset/independent valids without changing payload layout.
module dp_tb;
  `include "dp_functions.vh"
  parameter integer K_FP16=`DP_DEFAULT_K, LOCAL_W=`DP_DEFAULT_LOCAL_W, GLOBAL_W=`DP_DEFAULT_GLOBAL_W;
  // Largest current campaign has 1053 requests; retain a checked 2048-row buffer.
  // This is testbench storage only; no DUT capacity/parameters are changed.
  localparam integer G=K_FP16/`DP_GROUP_H, CAPACITY=2048;
  reg clock=0;
  always #5 clock=~clock;
  reg reset=1,in_a_valid=0,in_b_valid=0,in_c_valid=0,in_c_datatype=0,in_last=0;
  reg [K_FP16*`DP_HALF_W-1:0] in_a=0,in_b=0;
  reg [`DP_TYPE_W-1:0] in_a_datatype=0,in_b_datatype=0;
  reg [G*`DP_SCALE_W-1:0] in_scale_a,in_scale_b;
  reg [`DP_SCALE_TYPE_W-1:0] in_scale_a_datatype,in_scale_b_datatype;
  reg [G*4-1:0] in_hif4_e1_a=0,in_hif4_e1_b=0;
  reg [G*2-1:0] in_hif4_e2_a=0,in_hif4_e2_b=0;
  reg [`DP_FP32_W-1:0] in_c=0;
  wire out_a_ready,out_b_ready,out_c_ready,out_valid,out_d_datatype,out_last;
  wire [`DP_FP32_W-1:0] out_d;
  dp_top #(.K_FP16(K_FP16),.LOCAL_W(LOCAL_W),.GLOBAL_W(GLOBAL_W)) dut(
    .clock(clock),
    .reset(reset),
    .in_a_valid(in_a_valid),
    .in_b_valid(in_b_valid),
    .in_c_valid(in_c_valid),
    .out_a_ready(out_a_ready),
    .out_b_ready(out_b_ready),
    .out_c_ready(out_c_ready),
    .in_a(in_a),
    .in_b(in_b),
    .in_a_datatype(in_a_datatype),
    .in_b_datatype(in_b_datatype),
    .in_scale_a(in_scale_a),
    .in_scale_b(in_scale_b),
    .in_scale_a_datatype(in_scale_a_datatype),
    .in_scale_b_datatype(in_scale_b_datatype),
    .in_hif4_e1_a(in_hif4_e1_a),
    .in_hif4_e1_b(in_hif4_e1_b),
    .in_hif4_e2_a(in_hif4_e2_a),
    .in_hif4_e2_b(in_hif4_e2_b),
    .in_c(in_c),
    .in_c_datatype(in_c_datatype),
    .in_last(in_last),
    .out_valid(out_valid),
    .out_d(out_d),
    .out_d_datatype(out_d_datatype),
    .out_last(out_last)
  );
  integer ids[0:CAPACITY-1],ats[0:CAPACITY-1],bts[0:CAPACITY-1],cts[0:CAPACITY-1],asts[0:CAPACITY-1],bsts[0:CAPACITY-1],lasts[0:CAPACITY-1];
  reg [K_FP16*`DP_HALF_W-1:0] aa[0:CAPACITY-1],bb[0:CAPACITY-1];
  reg [`DP_FP32_W-1:0] cc[0:CAPACITY-1],expected[0:CAPACITY-1];
  reg [G*`DP_SCALE_W-1:0] sa[0:CAPACITY-1],sb[0:CAPACITY-1];
  reg [G*4-1:0] ae1[0:CAPACITY-1],be1[0:CAPACITY-1];
  reg [G*2-1:0] ae2[0:CAPACITY-1],be2[0:CAPACITY-1];
  integer pending[0:`DP_BASE_LATENCY-1],pending_id,expected_valid;
  integer fd,gd,sd,od,trace_fd,n,k,rc,row,cycle=0,accepted=0,checked=0,cancelled=0,ev_reset,av,bv,cv,legal;
  reg [4095:0] inputs_path,golden_path,schedule_path,output_path,trace_path;
  reg [255:0] magic;
  integer i;
  task drive(input integer index);
    begin
      in_a=aa[index]; in_b=bb[index]; in_c=cc[index];
      in_a_datatype=(ats[index]); in_b_datatype=(bts[index]);
      in_c_datatype=(cts[index]); in_last=(lasts[index]);
      in_scale_a=sa[index]; in_scale_b=sb[index];
      in_scale_a_datatype=(asts[index]); in_scale_b_datatype=(bsts[index]);
      in_hif4_e1_a=ae1[index]; in_hif4_e2_a=ae2[index]; in_hif4_e1_b=be1[index]; in_hif4_e2_b=be2[index];
    end
  endtask
  initial begin
    if(!$value$plusargs("INPUTS=%s",inputs_path) || !$value$plusargs("GOLDEN=%s",golden_path) || !$value$plusargs("SCHEDULE=%s",schedule_path)) begin $display("FAIL "); $display("missing paths"); $finish; end
    if(!$value$plusargs("OUTPUT=%s",output_path)) output_path="dp_results.txt";
    od=$fopen(output_path,"w");
    trace_fd=0;
    if($value$plusargs("CUTPOINTS=%s",trace_path)) trace_fd=$fopen(trace_path,"w");
    fd=$fopen(inputs_path,"r"); gd=$fopen(golden_path,"r"); sd=$fopen(schedule_path,"r");
    if(!fd || !gd || !sd) begin $display("FAIL "); $display("cannot open inputs"); $finish; end
    rc=$fscanf(fd,"%s\n%d %d\n",magic,n,k);
    if(rc!=3 || magic!="DP_INPUTS_V1" || n>CAPACITY || k!=K_FP16) begin $display("FAIL "); $display("invalid input header"); $finish; end
    for(i=0;i<n;i=i+1) begin
      rc=$fscanf(fd,"%d %d %d %d %d %d %d %h %h %h %h %h %h %h %h %h\n",
        ids[i],ats[i],bts[i],cts[i],asts[i],bsts[i],lasts[i],aa[i],bb[i],cc[i],sa[i],sb[i],ae1[i],ae2[i],be1[i],be2[i]);
      if(rc!=16) begin $display("FAIL "); $display("bad input record %0d",i); $finish; end
      rc=$fscanf(gd,"%h\n",expected[i]); if(rc!=1) begin $display("FAIL "); $display("bad golden record"); $finish; end
    end
    for(i=0;i<`DP_BASE_LATENCY;i=i+1) pending[i]=-1;
    #1; drive(0);
    @(posedge clock); // Initialize all synchronous valid state.
    while(!$feof(sd)) begin
      @(negedge clock);
      rc=$fscanf(sd,"%d %d %d %d %d\n",ev_reset,av,bv,cv,row);
      if(rc!=5) begin $display("FAIL "); $display("invalid schedule at %0d",cycle); $finish; end
      reset=(ev_reset); in_a_valid=(av); in_b_valid=(bv); in_c_valid=(cv);
      if(row>=0) drive(row);
      @(posedge clock);
      legal=(in_a_datatype<=`DP_DT_INT8 && in_a_datatype==in_b_datatype &&
        in_c_datatype==(in_a_datatype==`DP_DT_INT8) &&
        in_scale_a_datatype==scale_type(in_a_datatype) && in_scale_b_datatype==scale_type(in_a_datatype));
      if({out_a_ready,out_b_ready,out_c_ready} !== {3{!reset && av!=0 && bv!=0 && cv!=0 && legal!=0}})
        begin $display("FAIL "); $display("atomic ready mismatch cycle %0d",cycle); $finish; end
      if(reset) begin
        for(i=0;i<`DP_BASE_LATENCY;i=i+1) begin
          if(pending[i]>=0) cancelled=cancelled+1;
          pending[i]=-1;
        end
      end else begin
        pending_id=pending[`DP_BASE_LATENCY-1]; expected_valid=(pending_id>=0);
        if(out_valid !== (expected_valid)) begin $display("FAIL "); $display("valid mismatch at cycle %0d",cycle); $finish; end
        if(expected_valid) begin
          if(out_d !== expected[pending_id] || out_last !== (lasts[pending_id]) || out_d_datatype !== (cts[pending_id])) begin
            $display("FAIL cycle=%0d row=%0d id=%0d mode=%0d got=%h expected=%h",cycle,pending_id,ids[pending_id],ats[pending_id],out_d,expected[pending_id]);
            begin $display("FAIL "); $display("result mismatch"); $finish; end
          end
          $fdisplay(od,"%0d %08h %0d %0d",ids[pending_id],out_d,out_d_datatype,out_last);
          checked=checked+1;
        end
        for(i=`DP_BASE_LATENCY-1;i>0;i=i-1) pending[i]=pending[i-1];
        pending[0]=-1;
        if(out_a_ready) begin
          if(row<0) begin $display("FAIL "); $display("accepted without source row"); $finish; end
          pending[0]=row; accepted=accepted+1;
        end
      end
      cycle=cycle+1;
    end
    if(accepted!=checked+cancelled) begin $display("FAIL "); $display("undrained pipeline"); $finish; end
    $fclose(od);
    if(trace_fd) $fclose(trace_fd);
    $display("PASS cycles=%0d accepted=%0d checked=%0d cancelled=%0d",cycle,accepted,checked,cancelled);
    $finish;
  end
  // Observational only: values are sampled halfway after the updating edge.
  // Generic packed fields work for both plain Verilog vectors and packed SV structs.
  genvar group_index,lane_index;
  generate for(group_index=0;group_index<G;group_index=group_index+1) begin: g_trace_group
    for(lane_index=0;lane_index<`DP_LANES;lane_index=lane_index+1) begin: g_trace_lane
      integer element_index;
      always @(negedge clock) if(trace_fd) begin
        if(dut.valid_q[0]) begin
          for(element_index=0;element_index<(ats[pending[0]]==`DP_DT_TF32 ? 1 : `DP_LANES);element_index=element_index+1) begin
            $fdisplay(trace_fd,"%0d 1 layout_a %0d %h %h %h",pending[0],
              (group_index*`DP_LANES+lane_index)*(ats[pending[0]]==`DP_DT_TF32 ? 1 : `DP_LANES)+element_index,
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.operand_unpack_a.mantissa_q[element_index],
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.operand_unpack_a.exponent_q[element_index],
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.operand_unpack_a.signs_q[element_index]);
            $fdisplay(trace_fd,"%0d 1 layout_b %0d %h %h %h",pending[0],
              (group_index*`DP_LANES+lane_index)*(ats[pending[0]]==`DP_DT_TF32 ? 1 : `DP_LANES)+element_index,
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.operand_unpack_b.mantissa_q[element_index],
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.operand_unpack_b.exponent_q[element_index],
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.operand_unpack_b.signs_q[element_index]);
          end
        end
        if(dut.valid_q[1]) begin
          for(element_index=0;element_index<elements(ats[pending[1]][`DP_TYPE_W-1:0]);element_index=element_index+1)
            $fdisplay(trace_fd,"%0d 2 product %0d %h",pending[1],(group_index*`DP_LANES+lane_index)*elements(ats[pending[1]][`DP_TYPE_W-1:0])+element_index,
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.products_q[element_index*`DP_PRODUCT_W+:`DP_PRODUCT_W]);
          $fdisplay(trace_fd,"%0d 2 anchor %0d %h",pending[1],group_index,
              dut.g_group[group_index].group_unit.g_lane[lane_index].lane.anchor_s2_q);
        end
        if(dut.valid_q[2]) begin
          for(element_index=0;element_index<`DP_Q_LANES;element_index=element_index+1)
            $fdisplay(trace_fd,"%0d 3 leaf %0d %0d",pending[2],(group_index*`DP_LANES+lane_index)*`DP_Q_LANES+element_index,
              $signed(dut.g_group[group_index].group_unit.g_lane[lane_index].lane.leaves_q[element_index*(LOCAL_W+1)+:LOCAL_W+1]));
        end
        if(dut.valid_q[3]) $fdisplay(trace_fd,"%0d 4 lane %0d %0d",pending[3],group_index*`DP_LANES+lane_index,
              $signed(dut.g_group[group_index].group_unit.g_lane[lane_index].lane.out_sop));
      end
    end
    always @(negedge clock) if(trace_fd && dut.valid_q[4])
      $fdisplay(trace_fd,"%0d 5 group %0d %h %0d %0d %0d %h",pending[4],group_index,
        dut.g_group[group_index].magnitude,$signed(dut.g_group[group_index].anchor),dut.g_group[group_index].leading,
        dut.g_group[group_index].sign_value,dut.g_group[group_index].special_value);
  end endgenerate
  integer source_index;
  always @(negedge clock) if(trace_fd) begin
    if(dut.valid_q[4]) $fdisplay(trace_fd,"%0d 5 c 0 %h %0d %0d %0d %h",pending[4],dut.c_magnitude_q,
      $signed(dut.c_anchor_q),dut.c_z_q,dut.c_negative_q,dut.c_special_q);
    if(dut.valid_q[5]) begin
      for(source_index=0;source_index<G+1;source_index=source_index+1)
        $fdisplay(trace_fd,"%0d 6 aligned %0d %0d %0d",pending[5],source_index,
          $signed(dut.leaves_q[source_index*GLOBAL_W+:GLOBAL_W]),$signed(dut.common_s6_q));
    end
    if(dut.valid_q[6]) $fdisplay(trace_fd,"%0d 7 sum 0 %0d",pending[6],$signed(dut.sum_q));
  end

endmodule
