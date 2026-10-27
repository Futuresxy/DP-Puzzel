// Shared streaming file driver, compact logical-to-physical packing and protocol monitor.
  reg [15:0] a_elements[0:WORD_COUNT*4-1], b_elements[0:WORD_COUNT*4-1];
  reg [7:0] a_scale_data[0:SF_COUNT-1], b_scale_data[0:SF_COUNT-1];
  reg a_g0_data[0:WORD_COUNT-1],b_g0_data[0:WORD_COUNT-1];
  reg a_g1_data[0:G1_COUNT-1],b_g1_data[0:G1_COUNT-1];
  integer accepted_cycle[0:63];
  integer accepted=0,completed=0,cycle=0;
  integer txn_count,logical_k,schedule,a_scale_count,b_scale_count,g0_count,g1_count;
  integer source_fd,result_fd,trace_fd,protocol_fd,scan_ok;
  integer i,j,m,l,logical_base,word_base,sf_base,local_words,lanes,shift_bits;
  integer age,offered,delay_a,delay_c,cfg_wait;
  reg monitor_active=0,header_loaded=0,expected_valid;
  reg [31:0] token;
  string input_file,output_dir,rtl_id,magic,extra;

  function automatic integer element_lanes(input integer dtype);
    if(dtype==7 || dtype==8) element_lanes=1;
    else if(dtype>=3 && dtype<=6) element_lanes=2;
    else element_lanes=4;
  endfunction
  function automatic integer supports(input integer kind,input integer dtype);
    supports=(kind==0 || (kind==1 && dtype<=6) || (kind==2 && dtype<=2));
  endfunction
  task automatic read_token;
    begin
      scan_ok=$fscanf(source_fd,"%h",token);
      if(scan_ok!=1 || (^token)===1'bx) $fatal(1,"missing or invalid vector token at txn %0d",accepted);
    end
  endtask
  task automatic load_transaction(input integer index);
    integer elem_mask,bit_count;
    begin
      read_token(); if(token!=index) $fatal(1,"transaction ID mismatch");
      read_token();c_word=token;
      bit_count=(a_dtype==7 || a_dtype==8)?16:((a_dtype==3 || a_dtype==4)?6:((a_dtype>=3)?8:4));
      elem_mask=(1<<bit_count)-1;
      for(i=0;i<logical_k;i=i+1) begin
        read_token();if(token>elem_mask) $fatal(1,"A element encoding overflow");a_elements[i]=token;
      end
      for(i=0;i<logical_k;i=i+1) begin
        read_token();if(token>elem_mask) $fatal(1,"B element encoding overflow");b_elements[i]=token;
      end
      for(i=0;i<a_scale_count;i=i+1) begin read_token();if(token>255) $fatal(1,"A scale overflow");a_scale_data[i]=token;end
      for(i=0;i<b_scale_count;i=i+1) begin read_token();if(token>255) $fatal(1,"B scale overflow");b_scale_data[i]=token;end
      for(i=0;i<g0_count;i=i+1) begin read_token();if(token>1) $fatal(1,"A group0 overflow");a_g0_data[i]=token;end
      for(i=0;i<g0_count;i=i+1) begin read_token();if(token>1) $fatal(1,"B group0 overflow");b_g0_data[i]=token;end
      for(i=0;i<g1_count;i=i+1) begin read_token();if(token>1) $fatal(1,"A group1 overflow");a_g1_data[i]=token;end
      for(i=0;i<g1_count;i=i+1) begin read_token();if(token>1) $fatal(1,"B group1 overflow");b_g1_data[i]=token;end
      for(i=0;i<WORD_COUNT;i=i+1) begin a_words[i]=0;b_words[i]=0;a_group0[i]=0;b_group0[i]=0;end
      for(i=0;i<G1_COUNT;i=i+1) begin a_group1[i]=0;b_group1[i]=0;end
      for(i=0;i<SF_COUNT;i=i+1) begin
        a_scales[i]=(a_sf_type==1)?8'h38:((a_sf_type==3)?8'hc0:8'h7f);
        b_scales[i]=(b_sf_type==1)?8'h38:((b_sf_type==3)?8'hc0:8'h7f);
      end
      logical_base=0;word_base=0;sf_base=0;lanes=element_lanes(a_dtype);
      shift_bits=(lanes==1)?16:((lanes==2)?8:4);
      for(m=0;m<MID_COUNT;m=m+1) begin
        local_words=mid_words(m);
        if(supports(mid_kind(m),a_dtype) && supports(mid_kind(m),b_dtype)) begin
          for(j=0;j<local_words;j=j+1) begin
            for(l=0;l<lanes;l=l+1) begin
              a_words[word_base+j]=a_words[word_base+j] | (a_elements[logical_base+j*lanes+l] << (l*shift_bits));
              b_words[word_base+j]=b_words[word_base+j] | (b_elements[logical_base+j*lanes+l] << (l*shift_bits));
            end
          end
          if(a_dtype>=3 && a_dtype<=6) begin
            a_scales[sf_base]=a_scale_data[logical_base/32];
            b_scales[sf_base]=b_scale_data[logical_base/32];
          end else if(a_dtype==1) begin
            for(j=0;j<local_words*4/32;j=j+1) begin
              a_scales[sf_base+j]=a_scale_data[logical_base/32+j];
              b_scales[sf_base+j]=b_scale_data[logical_base/32+j];
            end
          end else if(a_dtype==0) begin
            for(j=0;j<local_words/4;j=j+1) begin
              a_scales[sf_base+j]=a_scale_data[logical_base/16+j];
              b_scales[sf_base+j]=b_scale_data[logical_base/16+j];
            end
          end else if(a_dtype==2) begin
            a_scales[sf_base]=a_scale_data[logical_base/64];
            b_scales[sf_base]=b_scale_data[logical_base/64];
            for(j=0;j<local_words;j=j+1) begin
              a_group0[word_base+j]=a_g0_data[logical_base/4+j];
              b_group0[word_base+j]=b_g0_data[logical_base/4+j];
            end
            for(j=0;j<local_words/2;j=j+1) begin
              a_group1[word_base/2+j]=a_g1_data[logical_base/8+j];
              b_group1[word_base/2+j]=b_g1_data[logical_base/8+j];
            end
          end
          logical_base=logical_base+local_words*lanes;
        end
        word_base=word_base+local_words;sf_base=sf_base+local_words/4;
      end
      if(logical_base!=logical_k) $fatal(1,"file K does not match PE native K");
      input_last=(index==txn_count-1);
    end
  endtask

  // Sample all transfers before NBA at the rising edge. S01 accepts at edge N;
  // S18's result is transferred at edge N+18. Driving only on falling edges
  // prevents driver/monitor races and preserves payloads during admission stalls.
  always @(posedge clock) begin
    if (reset) begin
      accepted = 0;
      completed = 0;
      cycle = 0;
    end else if (monitor_active) begin
      cycle = cycle + 1;
      if ((^{cfg_ready, ab_ready, c_ready, result_valid, idle}) === 1'bx)
        $fatal(1, "unknown control at cycle %0d", cycle);
      if ((ab_valid && ab_ready) !== (c_valid && c_ready))
        $fatal(1, "AB/C handshake is not atomic at cycle %0d", cycle);
      if (accepted < txn_count && ab_valid && c_valid && !(ab_ready && c_ready))
        $fatal(1, "II=1 admission failed at txn %0d", accepted);
      if (accepted >= txn_count && completed < txn_count &&
          (ab_ready || c_ready || cfg_ready || idle))
        $fatal(1, "draining advertised admission or idle before final output");
      expected_valid = (completed < accepted &&
                        cycle - accepted_cycle[completed%64] == LATENCY);
      if (result_valid !== expected_valid)
        $fatal(1, "valid/latency mismatch cycle=%0d txn=%0d expected=%0d actual=%0d",
               cycle, completed, expected_valid, result_valid);
      if (result_valid) begin
        if (completed >= txn_count || (^result) === 1'bx)
          $fatal(1, "extra or X/Z result at txn %0d", completed);
        if (result_last !== (completed == txn_count-1))
          $fatal(1, "last mismatch at txn %0d", completed);
        $fdisplay(result_fd, "%08h", result);
        $fdisplay(trace_fd, "%0d\t%08h\t%0d\t%0d\t%0d\t%0d", completed,
                  result, accepted_cycle[completed%64], cycle,
                  cycle-accepted_cycle[completed%64], result_last);
        completed = completed + 1;
      end
      if (ab_valid && ab_ready) begin
        if (accepted >= txn_count) $fatal(1, "extra input admitted during drain");
        if (accepted-completed >= 64) $fatal(1,"scoreboard FIFO overflow");
        accepted_cycle[accepted%64] = cycle;
        accepted = accepted + 1;
      end
    end
  end


  initial begin
    if(!$value$plusargs("INPUT_FILE=%s",input_file)) $fatal(1,"missing INPUT_FILE");
    if(!$value$plusargs("OUTPUT_DIR=%s",output_dir)) $fatal(1,"missing OUTPUT_DIR");
    if(!$value$plusargs("RTL_ID=%s",rtl_id)) $fatal(1,"missing RTL_ID");
    if(!$value$plusargs("SCHEDULE=%d",schedule)) schedule=0;
    if(schedule!=0 && schedule!=1) $fatal(1,"invalid schedule");
    source_fd=$fopen(input_file,"r");if(!source_fd) $fatal(1,"cannot open inputs");
    scan_ok=$fscanf(source_fd,"%s",magic);
    if(scan_ok!=1 || magic!="PE_VECTORS_V2") $fatal(1,"bad input format");
    scan_ok=$fscanf(source_fd,"%d %d %d %d %d %d %d %d %d %d %d %d %d",txn_count,logical_k,
      a_dtype,b_dtype,a_sf_type,b_sf_type,c_type,out_type,rm,a_scale_count,b_scale_count,g0_count,g1_count);
    if(scan_ok!=13 || txn_count<=0 || logical_k<=0 || logical_k>WORD_COUNT*4 || a_dtype!=b_dtype ||
       a_scale_count>SF_COUNT || b_scale_count>SF_COUNT || g0_count>WORD_COUNT || g1_count>G1_COUNT)
      $fatal(1,"invalid vector shape/configuration");
    header_loaded=1;
    result_fd=$fopen({output_dir,"/rtl_result.txt"},"w");
    trace_fd=$fopen({output_dir,"/transactions.txt"},"w");
    protocol_fd=$fopen({output_dir,"/protocol.txt"},"w");
    if(!result_fd || !trace_fd || !protocol_fd) $fatal(1,"cannot open outputs");
    $fdisplay(protocol_fd,"RTL_ID %s\nINPUT_FILE %s",rtl_id,input_file);
    $fdisplay(trace_fd,"txn\tresult_hex\taccept_cycle\tresult_cycle\tlatency\tlast");
    repeat(4) @(negedge clock);
    reset=0;cfg_valid=1;cfg_wait=0;
    while(!cfg_ready && cfg_wait<20) begin @(negedge clock);cfg_wait=cfg_wait+1;end
    if(!cfg_ready) $fatal(1,"cfg timeout");
    @(posedge clock);@(negedge clock);
    cfg_valid=0;monitor_active=1;offered=-1;age=0;
    while(accepted<txn_count) begin
      if(offered!=accepted) begin offered=accepted;age=0;load_transaction(offered);end
      delay_a=0;delay_c=0;
      if(schedule==1 && offered>=32) begin
        if(offered%7==0) begin delay_a=2;delay_c=2;end
        if(offered%11==0) delay_c=delay_c+2;
        if(offered%13==0) delay_a=delay_a+1;
      end
      ab_valid=(age>=delay_a);c_valid=(age>=delay_c);
      @(negedge clock);age=age+1;
    end
    scan_ok=$fscanf(source_fd,"%s",extra);if(scan_ok==1) $fatal(1,"extra input tokens");
    $fclose(source_fd);
    ab_valid=1;c_valid=1;
    wait(completed==txn_count);@(negedge clock);
    ab_valid=0;c_valid=0;
    if(!idle || !cfg_ready) $fatal(1,"Idle not restored");
    repeat(8) @(negedge clock);monitor_active=0;
    $fdisplay(protocol_fd,"accepted %0d\ncompleted %0d\nlatency %0d\nschedule %0d",accepted,completed,LATENCY,schedule);
    $fclose(result_fd);$fclose(trace_fd);$fclose(protocol_fd);
    $display("PROTOCOL_PASS RTL_ID=%s accepted=%0d completed=%0d latency=%0d schedule=%0d",rtl_id,accepted,completed,LATENCY,schedule);
    $finish;
  end
  initial begin
    wait(header_loaded);
    // Scales with transaction count; no fixed MAX_TXN or whole-batch buffers.
    #(10.0*(txn_count*6.0+256.0));
    $fatal(1,"simulation timeout");
  end
