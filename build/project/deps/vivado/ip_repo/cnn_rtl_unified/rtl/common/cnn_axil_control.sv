`timescale 1ns/1ps
`include "cnn_unified_contract.vh"
// 完整控制寄存器/输入窗口；core端在S5接真实整网。CORE.done必须在流水排空后发出。
module cnn_axil_control (
    input wire clk, input wire resetn,
    input wire [15:0] s_axi_awaddr, input wire s_axi_awvalid, output wire s_axi_awready,
    input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb, input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [1:0] s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
    input wire [15:0] s_axi_araddr, input wire s_axi_arvalid, output wire s_axi_arready,
    output reg [31:0] s_axi_rdata, output reg [1:0] s_axi_rresp, output reg s_axi_rvalid, input wire s_axi_rready,
    output reg core_start, output reg core_abort, output reg core_clear,
    output reg [31:0] model_weight_base, output reg [31:0] model_bias_base,
    output reg [31:0] compute_limit_cycles, output reg [31:0] ddr_stall_limit_cycles,
    input wire core_quiescent, input wire core_done, input wire core_error, input wire [3:0] core_error_code,
    input wire core_recovery_required, input wire core_protocol_poisoned, input wire [7:0] core_stage,
    input wire core_ar_pending, input wire core_outstanding,
    input wire [31:0] core_pool2_bytes, input wire [31:0] core_pool3_bytes,
    input wire [31:0] core_ar_count, input wire [31:0] core_r_count, input wire [31:0] core_last_araddr,
    input wire [3:0] core_last_r_meta, input wire [31:0] core_fault_flags,
    input wire core_logit_valid, input wire [4:0] core_logit_index, input wire signed [31:0] core_logit,
    input wire core_input_read, input wire [11:0] core_input_address,
    output wire [7:0] core_input_data, output wire core_input_valid,
    output reg debug_request, output reg [1:0] debug_select, output reg [13:0] debug_index,
    input wire debug_valid, input wire [7:0] debug_data,
    output wire quiescent, output wire [3:0] control_state
);
    localparam [3:0] IDLE=0,RUN=1,DONE=7,DRAIN=8,ERROR_SAFE=9,ERROR_UNSAFE=10;
    reg [3:0] state;
    reg [31:0] config_reg [0:8];
    reg [31:0] error_code,transaction_seq,result_seq,error_detail,local_fault_flags;
    reg [63:0] cycles;
    reg [31:0] cycles_hi_snapshot,drain_cycles;
    reg result_valid;
    reg [1023:0] input_valid_map;
    reg [10:0] valid_words;
    reg [31:0] transaction_input_bytes;
    reg signed [31:0] logits [0:21];
    reg [21:0] logits_written;
    reg [5:0] logit_count;
    reg aw_pending,w_pending;
    reg [15:0] aw_saved;
    reg [31:0] w_saved;
    reg [3:0] strobe_saved;
    reg input_write,input_read;
    reg [9:0] input_word_address;
    reg [31:0] input_write_data;
    wire [31:0] input_read_data;
    wire input_read_valid;
    reg input_read_pending,debug_read_pending;
    reg [1:0] core_input_pending;
    reg [31:0] debug_selector_reg,debug_index_reg;
    wire active=state==RUN || state==DRAIN;
    assign control_state=state;
    wire backend_safe=core_quiescent && !core_recovery_required && !core_protocol_poisoned &&
                      !core_ar_pending && !core_outstanding && core_input_pending==0;
    assign quiescent=!active && state!=ERROR_UNSAFE && backend_safe &&
                    !input_read_pending && !debug_read_pending && !input_write && !input_read;
    wire [32:0] weight_end={1'b0,config_reg[0]}+{1'b0,config_reg[2]};
    wire [32:0] bias_end={1'b0,config_reg[3]}+{1'b0,config_reg[5]};
    wire config_valid=config_reg[0]!=0 && config_reg[3]!=0 &&
        config_reg[0][5:0]==0 && config_reg[3][5:0]==0 &&
        config_reg[1]==169248 && config_reg[2]==169280 && config_reg[4]==472 && config_reg[5]==512 &&
        weight_end<=33'h040000000 && bias_end<=33'h040000000 &&
        (weight_end<={1'b0,config_reg[3]} || bias_end<={1'b0,config_reg[0]}) &&
        config_reg[6]==32'hb91cb580 && config_reg[7]!=0 && config_reg[8]!=0;
    wire [31:0] byte_mask={{8{strobe_saved[3]}},{8{strobe_saved[2]}},{8{strobe_saved[1]}},{8{strobe_saved[0]}}};
    wire [31:0] command=w_saved & byte_mask;
    wire write_execute=aw_pending && w_pending && !s_axi_bvalid;
    wire abort_command=write_execute && aw_saved==16'h0004 && command==4;
    assign s_axi_awready=resetn && !aw_pending && !s_axi_bvalid && !input_read_pending && !debug_read_pending;
    assign s_axi_wready=resetn && !w_pending && !s_axi_bvalid && !input_read_pending && !debug_read_pending;
    assign s_axi_arready=resetn && !s_axi_rvalid && !input_read_pending && !debug_read_pending &&
        !aw_pending && !w_pending && !s_axi_awvalid && !s_axi_wvalid && !input_write && !input_read;
    wire [31:0] status_word={23'd0,(valid_words==1024),config_valid,
        (core_recovery_required||state==ERROR_UNSAFE),(state==DRAIN),result_valid,
        (error_code!=0),(state==DONE),active,quiescent};
    wire debug_safe=state==DONE && quiescent && result_valid;
    wire debug_range=(debug_selector_reg==1 && debug_index_reg<12288) ||
        (debug_selector_reg==2 && debug_index_reg<3072) || (debug_selector_reg==3 && debug_index_reg<48);
    wire [7:0] completion_error=!backend_safe ? 8'd11 : core_pool2_bytes!=12288 ? 8'd8 :
                                core_pool3_bytes!=3072 ? 8'd9 : 8'd10;
    integer i;
    cnn_input_store input_store (
        .clk(clk),.resetn(resetn),.cpu_write(input_write),.cpu_read(input_read),
        .cpu_word_address(input_word_address),.cpu_write_data(input_write_data),
        .cpu_read_data(input_read_data),.cpu_read_valid(input_read_valid),
        .core_read(core_input_read && state==RUN),.core_byte_address(core_input_address),
        .core_read_data(core_input_data),.core_read_valid(core_input_valid)
    );
    always @(posedge clk) begin
        if (!resetn) begin
            state<=IDLE;error_code<=0;transaction_seq<=0;result_seq<=0;error_detail<=0;local_fault_flags<=0;
            cycles<=0;cycles_hi_snapshot<=0;drain_cycles<=0;result_valid<=0;
            input_valid_map<=0;valid_words<=0;transaction_input_bytes<=0;logits_written<=0;logit_count<=0;
            aw_pending<=0;w_pending<=0;aw_saved<=0;w_saved<=0;strobe_saved<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            input_write<=0;input_read<=0;input_word_address<=0;input_write_data<=0;
            input_read_pending<=0;debug_read_pending<=0;core_input_pending<=0;debug_request<=0;debug_select<=0;debug_index<=0;
            debug_selector_reg<=0;debug_index_reg<=0;core_start<=0;core_abort<=0;core_clear<=0;
            model_weight_base<=0;model_bias_base<=0;compute_limit_cycles<=100000000;ddr_stall_limit_cycles<=10000000;
            for (i=0;i<9;i=i+1) config_reg[i]<=0;
            config_reg[7]<=100000000;config_reg[8]<=10000000;
        end else begin
            core_start<=0;core_abort<=0;core_clear<=0;input_write<=0;input_read<=0;debug_request<=0;
            core_input_pending<={core_input_pending[0],(core_input_read && state==RUN)};
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if (s_axi_awvalid && s_axi_awready) begin aw_pending<=1;aw_saved<=s_axi_awaddr;end
            if (s_axi_wvalid && s_axi_wready) begin w_pending<=1;w_saved<=s_axi_wdata;strobe_saved<=s_axi_wstrb;end
            if (input_read_pending && input_read_valid) begin
                input_read_pending<=0;s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=input_read_data;
            end
            if (debug_read_pending && debug_valid) begin
                debug_read_pending<=0;s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<={24'd0,debug_data};
            end
            if (active) cycles<=cycles+1'b1;
            if (state==DRAIN) begin
                if (drain_cycles!=32'hffffffff) drain_cycles<=drain_cycles+1'b1;
                if (core_protocol_poisoned) state<=ERROR_UNSAFE;
                else if (backend_safe) state<=ERROR_SAFE;
            end
            if (state==RUN) begin
                if (core_logit_valid) begin
                    if (core_logit_index<22 && !logits_written[core_logit_index]) begin
                        logits[core_logit_index]<=core_logit;logits_written[core_logit_index]<=1;
                        logit_count<=logit_count+1'b1;
                    end else begin
                        state<=DRAIN;core_abort<=1;error_code<=10;local_fault_flags[5]<=1;result_valid<=0;
                        error_detail<={16'd0,8'd10,core_stage};
                    end
                end
                if (core_done && !abort_command) begin
                    if (backend_safe && core_pool2_bytes==12288 && core_pool3_bytes==3072 &&
                        logit_count==22 && &logits_written && !(core_logit_valid &&
                        (core_logit_index>=22 || logits_written[core_logit_index]))) begin
                        state<=DONE;result_valid<=1;result_seq<=transaction_seq;
                    end else begin
                        state<=DRAIN;core_abort<=1;result_valid<=0;local_fault_flags[5]<=1;
                        error_code<={24'd0,completion_error};error_detail<={16'd0,completion_error,core_stage};
                    end
                end
                if (cycles>={32'd0,compute_limit_cycles}-1'b1 && !core_done) begin
                    state<=DRAIN;core_abort<=1;result_valid<=0;local_fault_flags[6]<=1;
                    if (error_code==0) begin error_code<=2;error_detail<={16'd0,8'd2,core_stage};end
                end
                if (core_error) begin
                    state<=DRAIN;core_abort<=1;result_valid<=0;
                    if (error_code==0) begin error_code<=core_error_code==0 ? 11 : {28'd0,core_error_code};
                        error_detail<={16'd0,4'd0,core_error_code,core_stage};end
                end
            end
            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rdata<=0;s_axi_rresp<=0;s_axi_rvalid<=1;
                if (s_axi_araddr[1:0]!=0) s_axi_rresp<=2;
                else if (s_axi_araddr>=16'h1000 && s_axi_araddr<16'h2000) begin
                    if (state!=IDLE || !input_valid_map[s_axi_araddr[11:2]]) s_axi_rresp<=2;
                    else begin input_word_address<=s_axi_araddr[11:2];input_read<=1;input_read_pending<=1;s_axi_rvalid<=0;end
                end else if (s_axi_araddr>=16'h4000 && s_axi_araddr<16'h4058) begin
                    if (!result_valid || state!=DONE) s_axi_rresp<=2;
                    else s_axi_rdata<=logits[(s_axi_araddr-16'h4000)>>2];
                end else begin
                    case (s_axi_araddr)
                        `include "cnn_control_ro_cases.vh"
                        16'h0008:s_axi_rdata<=status_word;
                        16'h000c:s_axi_rdata<=error_code;
                        16'h0010:s_axi_rdata<=transaction_seq;
                        16'h0014:s_axi_rdata<=state==RUN ? {24'd0,core_stage} : {28'd0,state};
                        16'h0018:s_axi_rdata<=state==IDLE ? {19'd0,valid_words,2'b00} : transaction_input_bytes;
                        16'h001c:s_axi_rdata<=core_pool2_bytes;
                        16'h0020:s_axi_rdata<=core_pool3_bytes;
                        16'h0024:s_axi_rdata<={26'd0,logit_count};
                        16'h0028:begin s_axi_rdata<=cycles[31:0];cycles_hi_snapshot<=cycles[63:32];end
                        16'h002c:s_axi_rdata<=cycles_hi_snapshot;
                        16'h0030:s_axi_rdata<={31'd0,core_outstanding};
                        16'h0034:s_axi_rdata<={31'd0,core_ar_pending};
                        16'h0038:s_axi_rdata<=core_last_araddr;
                        16'h003c:s_axi_rdata<=core_r_count>32'h1fffffff ? 32'hffffffff : core_r_count<<3;
                        16'h0040,16'h0044,16'h0048,16'h004c,16'h0050,16'h0054,16'h0058,16'h005c,16'h0060:
                            s_axi_rdata<=config_reg[(s_axi_araddr-16'h0040)>>2];
                        16'h0064:s_axi_rdata<=error_detail;
                        16'h0068:s_axi_rdata<={28'd0,core_last_r_meta};
                        16'h0078:s_axi_rdata<=core_ar_count;
                        16'h007c:s_axi_rdata<=core_r_count;
                        16'h00a0:s_axi_rdata<=debug_selector_reg;
                        16'h00a4:s_axi_rdata<=debug_index_reg;
                        16'h00a8:if (debug_safe && debug_range) begin
                            debug_request<=1;debug_select<=debug_selector_reg[1:0];debug_index<=debug_index_reg[13:0];
                            debug_read_pending<=1;s_axi_rvalid<=0;
                        end else s_axi_rresp<=2;
                        16'h00c8:s_axi_rdata<=drain_cycles;
                        16'h00cc:s_axi_rdata<=local_fault_flags|core_fault_flags;
                        16'h00d0:s_axi_rdata<=result_seq;
                        default:s_axi_rresp<=2;
                    endcase
                end
            end
            if (write_execute) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if (aw_saved[1:0]!=0) s_axi_bresp<=2;
                else if (aw_saved>=16'h1000 && aw_saved<16'h2000) begin
                    if (strobe_saved==0) begin end
                    else if (state!=IDLE || strobe_saved!=4'hf) s_axi_bresp<=2;
                    else begin
                        input_write<=1;input_word_address<=aw_saved[11:2];input_write_data<=w_saved;
                        if (!input_valid_map[aw_saved[11:2]]) begin
                            input_valid_map[aw_saved[11:2]]<=1;valid_words<=valid_words+1'b1;
                        end
                    end
                end else if (aw_saved>=16'h0040 && aw_saved<=16'h0060) begin
                    if (strobe_saved==0) begin end
                    else if (state!=IDLE || !quiescent) s_axi_bresp<=2;
                    else config_reg[(aw_saved-16'h0040)>>2]<=
                        (config_reg[(aw_saved-16'h0040)>>2]&~byte_mask)|(w_saved&byte_mask);
                end else if (aw_saved==16'h00a0 || aw_saved==16'h00a4) begin
                    if (strobe_saved==0) begin end
                    else if (!debug_safe) s_axi_bresp<=2;
                    else if (aw_saved==16'h00a0) debug_selector_reg<=(debug_selector_reg&~byte_mask)|(w_saved&byte_mask);
                    else debug_index_reg<=(debug_index_reg&~byte_mask)|(w_saved&byte_mask);
                end else if (aw_saved==16'h0004) begin
                    case (command)
                        0:begin end
                        1:if (state==IDLE && quiescent && valid_words==1024 && config_valid) begin
                            state<=RUN;core_start<=1;core_clear<=1;transaction_seq<=transaction_seq+1'b1;
                            cycles<=0;drain_cycles<=0;error_code<=0;error_detail<=0;local_fault_flags<=0;
                            transaction_input_bytes<=4096;input_valid_map<=0;valid_words<=0;
                            result_valid<=0;logits_written<=0;logit_count<=0;
                            model_weight_base<=config_reg[0];model_bias_base<=config_reg[3];
                            compute_limit_cycles<=config_reg[7];ddr_stall_limit_cycles<=config_reg[8];
                        end else s_axi_bresp<=2;
                        2:if (state==DONE && quiescent) begin
                            state<=IDLE;result_valid<=0;input_valid_map<=0;valid_words<=0;transaction_input_bytes<=0;core_clear<=1;
                        end else s_axi_bresp<=2;
                        4:if (state==RUN || state==DRAIN) begin
                            state<=DRAIN;core_abort<=1;result_valid<=0;local_fault_flags[7]<=1;
                            if (error_code==0) begin error_code<=1;error_detail<={16'd0,8'd1,core_stage};end
                        end else s_axi_bresp<=2;
                        8:if ((state==IDLE || state==ERROR_SAFE) && quiescent) begin
                            state<=IDLE;result_valid<=0;input_valid_map<=0;valid_words<=0;transaction_input_bytes<=0;
                            error_code<=0;error_detail<=0;local_fault_flags<=0;cycles<=0;drain_cycles<=0;
                            logit_count<=0;logits_written<=0;core_clear<=1;
                        end else s_axi_bresp<=2;
                        default:s_axi_bresp<=2;
                    endcase
                end else s_axi_bresp<=2;
            end
        end
    end
endmodule
