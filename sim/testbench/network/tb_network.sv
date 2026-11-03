`timescale 1ns/1ps
module tb_network;
`include "fixture.vh"
    // Wave probes for the four Conv3 MAC outputs.
    wire signed [31:0] conv3_acc0 = dut.core.c3.mac_acc[0];
    wire signed [31:0] conv3_acc1 = dut.core.c3.mac_acc[1];
    wire signed [31:0] conv3_acc2 = dut.core.c3.mac_acc[2];
    wire signed [31:0] conv3_acc3 = dut.core.c3.mac_acc[3];
    reg[7:0]image[0:4095],a1[0:98303],p1[0:24575],a2[0:49151],p2[0:12287],a3[0:12287],p3[0:3071],hidden[0:47];
    reg[31:0]c1[0:98303],c2[0:49151],c3[0:12287],fc1[0:47],logits[0:21];
    integer case_id=-1,first_case=0,case_count=1,i,lane,index,wait_cycles,cycles,ninput,nc1,na1,np1,np2,nc2,na2,nc3,na3,np3,nfc1,nh,nlogit,loads,frontend_done;
    integer lc2[0:1],la2[0:1],lp2[0:1];integer output_checks=0,frame_count=0;reg score=0;reg[31:0]word_data;string path;
    always@(posedge clk)if(score)begin
        cycles=cycles+1;if(cycles>12000000)$fatal(1,"network timeout phase=%d",dut.core.phase);
        if(dut.core_error || dut.control_state==9 || dut.control_state==10)$fatal(1,"network error case=%d code=%d stage=%d ctrlcode=%d",case_id,dut.code,dut.stage,dut.control.error_code);
        if(dut.core.front_image_valid&&dut.core.front_ready)begin if(dut.core.feed_data!==image[ninput])$fatal(1,"input feeder");ninput=ninput+1;end
        if(dut.core.model_load&&dut.core.load_ready)loads=loads+1;
        if(dut.core.c3.diagnostic_acc_valid)begin index=dut.core.c3.diagnostic_address;if(dut.core.c3.diagnostic_acc!==c3[index])$fatal(1,"Conv3 acc index=%d",index);nc3=nc3+1;end
        if(dut.core.c3.diagnostic_activation_valid)begin index=dut.core.c3.diagnostic_address;if(dut.core.c3.diagnostic_activation!==a3[index])$fatal(1,"Conv3 activation");na3=na3+1;end
        if(dut.core.use_c3&&dut.core.p3_write)begin if(dut.core.p3_write_data!==p3[dut.core.p3_write_address])$fatal(1,"Pool3");np3=np3+1;end
        if(dut.core.fc.diagnostic_partial_valid&&!dut.core.fc.diagnostic_fc2&&dut.core.fc.diagnostic_chunk==5)begin
            if(dut.core.fc.diagnostic_acc!==fc1[dut.core.fc.diagnostic_output_index])$fatal(1,"FC1 acc");nfc1=nfc1+1;end
        if(dut.core.fc.diagnostic_hidden_valid)begin if(dut.core.fc.diagnostic_hidden!==hidden[dut.core.fc.diagnostic_output_index])$fatal(1,"FC1 hidden");nh=nh+1;end
        if(dut.logit_valid)begin if(dut.logit!==logits[dut.logit_index])$fatal(1,"logits index=%d got=%d expected=%d",dut.logit_index,dut.logit,$signed(logits[dut.logit_index]));nlogit=nlogit+1;end
        #1;
        if(dut.core.frontend.conv2_group_start)for(lane=0;lane<2;lane=lane+1)begin lc2[lane]=0;la2[lane]=0;lp2[lane]=0;end
        if(dut.core.frontend.conv_rslt_out_valid_layer1)begin if(dut.core.frontend.conv_rslt_out_layer1!==c1[nc1])$fatal(1,"Conv1 acc case=%d index=%d got=%d exp=%d",case_id,nc1,dut.core.frontend.conv_rslt_out_layer1,$signed(c1[nc1]));nc1=nc1+1;end
        if(dut.core.frontend.conv_rslt_act_valid_layer1)begin if(dut.core.frontend.conv_rslt_act_layer1!==a1[na1])$fatal(1,"Conv1 act");na1=na1+1;end
        if(dut.core.frontend.pool_data_vld_layer1)begin if(dut.core.frontend.pool_data_layer1!==p1[np1])$fatal(1,"Pool1");np1=np1+1;end
        for(lane=0;lane<2;lane=lane+1)begin
            if(dut.core.frontend.conv2_rslt_valid[lane])begin index=(dut.core.frontend.conv2_active_group_oc+lane)*1024+lc2[lane];if(dut.core.frontend.conv2_rslt_bus[lane*32+:32]!==c2[index])$fatal(1,"Conv2 acc case=%d index=%d",case_id,index);lc2[lane]=lc2[lane]+1;nc2=nc2+1;end
            if(dut.core.frontend.conv2_act_valid[lane])begin index=(dut.core.frontend.conv2_active_group_oc+lane)*1024+la2[lane];if(dut.core.frontend.conv2_act_bus[lane*8+:8]!==a2[index])$fatal(1,"Conv2 act");la2[lane]=la2[lane]+1;na2=na2+1;end
            if(dut.core.frontend.pool2_lane_valid[lane])begin index=(dut.core.frontend.conv2_active_group_oc+lane)*256+lp2[lane];if(dut.core.frontend.pool2_lane_data[lane*8+:8]!==p2[index])$fatal(1,"Pool2 lane");lp2[lane]=lp2[lane]+1;end
        end
        if(dut.core.front_valid)begin if(dut.core.front_data!==p2[np2])$fatal(1,"Pool2 CHW");np2=np2+1;end
        if(dut.core.front_done)begin frontend_done=frontend_done+1;if(dut.control_state!=1||dut.core_done||np2!=12288)$fatal(1,"frontend prematurely published DONE");$display("S5_FRONTEND_PASS case=%0d cycles=%0d",case_id,cycles);$fflush();end
    end
    task load_case(input integer id);begin
        path=$sformatf("%s/%03d_input_uint8.mem",`S5_VECTOR_DIR,id);$readmemh(path,image);
        path=$sformatf("%s/%03d_conv1_acc_int32.mem",`S5_VECTOR_DIR,id);$readmemh(path,c1);
        path=$sformatf("%s/%03d_conv1_relu_int8.mem",`S5_VECTOR_DIR,id);$readmemh(path,a1);
        path=$sformatf("%s/%03d_pool1_int8.mem",`S5_VECTOR_DIR,id);$readmemh(path,p1);
        path=$sformatf("%s/%03d_conv2_acc_int32.mem",`S5_VECTOR_DIR,id);$readmemh(path,c2);
        path=$sformatf("%s/%03d_conv2_relu_int8.mem",`S5_VECTOR_DIR,id);$readmemh(path,a2);
        path=$sformatf("%s/%03d_pool2_int8.mem",`S5_VECTOR_DIR,id);$readmemh(path,p2);
        path=$sformatf("%s/%03d_conv3_acc_int32.mem",`S5_VECTOR_DIR,id);$readmemh(path,c3);
        path=$sformatf("%s/%03d_conv3_relu_int8.mem",`S5_VECTOR_DIR,id);$readmemh(path,a3);
        path=$sformatf("%s/%03d_pool3_int8.mem",`S5_VECTOR_DIR,id);$readmemh(path,p3);
        path=$sformatf("%s/%03d_fc1_acc_int32.mem",`S5_VECTOR_DIR,id);$readmemh(path,fc1);
        path=$sformatf("%s/%03d_fc1_relu_int8.mem",`S5_VECTOR_DIR,id);$readmemh(path,hidden);
        path=$sformatf("%s/%03d_fc2_logits_int32.mem",`S5_VECTOR_DIR,id);$readmemh(path,logits);
    end endtask
    initial begin
        if($value$plusargs("FIRST=%d",first_case))begin end
        if($value$plusargs("COUNT=%d",case_count))begin end
        repeat(5)@(negedge clk);resetn=1;repeat(8)@(negedge clk);configure();
        read_bus(0,0,value);if(value!='h4352544c)$fatal(1,"unified identity");
        for(case_id=first_case;case_id<first_case+case_count;case_id=case_id+1)begin
            load_case(case_id);
            for(i=0;i<1024;i=i+1)begin word_data={image[i*4+3],image[i*4+2],image[i*4+1],image[i*4]};write_bus('h1000+i*4,word_data,0);end
            ninput=0;nc1=0;na1=0;np1=0;np2=0;nc2=0;na2=0;nc3=0;na3=0;np3=0;nfc1=0;nh=0;nlogit=0;loads=0;cycles=0;frontend_done=0;
            for(lane=0;lane<2;lane=lane+1)begin lc2[lane]=0;la2[lane]=0;lp2[lane]=0;end
            score=1;write_bus(4,1,0);
            wait(dut.core.phase==2);write_bus(4,1,2);write_bus('h1000,0,2);write_bus('h40,'h03000000,2);read_bus('h4000,2,value);
            while(dut.control_state!=7)@(negedge clk);score=0;
            if(ninput!=4096||nc1!=98304||na1!=98304||np1!=24576||nc2!=49152||na2!=49152||np2!=12288||nc3!=12288||na3!=12288||np3!=3072||nfc1!=48||nh!=48||nlogit!=22||loads!=359||frontend_done!=1)$fatal(1,"full network stage counts");
            if(!dut.core_quiet||dut.pending||dut.outstanding||dut.ar_count!=1372||dut.r_count!=21215)$fatal(1,"network DDR/drain counts AR=%d R=%d",dut.ar_count,dut.r_count);
            for(i=0;i<22;i=i+1)begin read_bus('h4000+i*4,0,value);if(value!==logits[i])$fatal(1,"committed logits");end
            read_bus('hd0,0,value);read_bus('h10,0,word_data);if(value!=word_data)$fatal(1,"result sequence");
            for(i=1;i<=3;i=i+1)begin
                write_bus('ha0,i,0);write_bus('ha4,0,0);read_bus('ha8,0,value);
                if(value[7:0] !== (i==1?p2[0]:i==2?p3[0]:hidden[0]))$fatal(1,"debug first byte");
                write_bus('ha4,i==1?12287:i==2?3071:47,0);read_bus('ha8,0,value);
                if(value[7:0] !== (i==1?p2[12287]:i==2?p3[3071]:hidden[47]))$fatal(1,"debug final byte");
            end
            output_checks=output_checks+359542;frame_count=frame_count+1;
            $display("S5_CASE_PASS index=%0d cycles=%0d input=4096 layer_values=359542 logits=22 loads=359 AR=1372 R=21215",case_id,cycles);$fflush();
            write_bus(4,2,0);read_bus('h4000,2,value);
        end
        $display("S5_PASS_NETWORK first=%0d count=%0d layer_values=%0d bus_writes=%0d bus_reads=%0d",first_case,frame_count,output_checks,bus_writes,bus_reads);$finish;
    end
endmodule
