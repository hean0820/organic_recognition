`timescale 1ns/1ps
// FC1: OUT/6 chunks/512 inputs. FC2: OUT/48 hidden inputs.
// The S2 MAC accumulator survives cache reloads; first is asserted once/neuron.
// Caller preloads the 472B bias region; external loader and quantizer are shared.
module cnn_fc (
    input wire clk, resetn, start, clear, abort,
    input wire [31:0] weight_base,
    output wire busy, output reg done, error, output reg [3:0] error_code,
    output wire pool3_read_enable, output wire [11:0] pool3_byte_address,
    input wire [7:0] pool3_data, input wire pool3_valid,
    output wire cache_load_valid, input wire cache_load_ready,
    output wire [31:0] cache_load_address, output wire [15:0] cache_load_bytes,
    input wire cache_loaded, cache_error, cache_quiescent,
    output wire cache_read_enable, output wire [9:0] cache_read_address,
    input wire [7:0] cache_data, input wire cache_valid,
    output wire quant_valid, output wire signed [31:0] quant_acc_s32,
    input wire quant_result_valid, input wire [7:0] quant_result,
    output wire logit_valid, output wire [4:0] logit_index, output wire signed [31:0] logit_s32,
    output reg [5:0] hidden_count, logit_count,
    output reg [4:0] argmax_index, output reg signed [31:0] argmax_score,
    output wire result_valid,
    input wire [5:0] hidden_debug_index,
    output wire [7:0] hidden_debug_data, output wire hidden_debug_valid,
    output wire diagnostic_partial_valid, output wire diagnostic_fc2,
    output wire [5:0] diagnostic_output_index, output wire [2:0] diagnostic_chunk,
    output wire signed [31:0] diagnostic_acc,
    output wire diagnostic_hidden_valid, output wire [7:0] diagnostic_hidden
);
    localparam IDLE=0, BIAS=1, BIAS_WAIT=2, LOAD=3, LOAD_WAIT=4,
               ISSUE=5, MAC_WAIT=6, QUANT_WAIT=7, NEXT=8, DRAIN=9, FAULT=10;
    reg [3:0] state;
    reg fc2,valid_result;
    reg [5:0] out_index;
    reg [2:0] chunk;
    reg [8:0] term;
    reg [1:0] bias_issue,bias_return;
    reg signed [31:0] bias;
    reg [31:0] base_latched,block_address;
    reg [4:0] drain;
    reg [7:0] hidden[0:47];
    reg [47:0] hidden_valid;
    reg [7:0] hidden0,hidden1;
    reg [1:0] hidden_pipe,issue_pipe,bias_pipe,first_pipe,last_pipe;
    wire stop=abort || error || cache_error;
    wire issue=state==ISSUE && !stop;
    wire bias_read=state==BIAS && !stop;
    wire last_term=fc2 ? term==47 : term==511;
    wire [7:0] activation=fc2?hidden1:pool3_data;
    wire activation_valid=fc2?hidden_pipe[1]:pool3_valid;
    wire bad_response=(issue_pipe[1] && (!cache_valid || !activation_valid)) || (bias_pipe[1] && !cache_valid);
    wire bad_value=issue_pipe[1] && (activation>127 || cache_data==8'h80);
    wire bad_hidden=issue && fc2 && (term>=48 || !hidden_valid[term[5:0]]);
    wire mac_done,mac_overflow;
    wire signed [31:0] mac_acc;
    wire accepted_mac=issue_pipe[1] && !stop && !bad_response && !bad_value;
    wire good_sum=state==MAC_WAIT && mac_done && !stop && !mac_overflow;
    assign busy=state!=IDLE && state!=FAULT;
    assign result_valid=valid_result && !busy && !stop && !clear;
    assign cache_load_valid=state==LOAD && !stop;
    assign cache_load_address=block_address;
    assign cache_load_bytes=fc2?16'd48:16'd512;
    assign cache_read_enable=issue || bias_read;
    assign cache_read_address=bias_read ? (10'd512+(fc2?10'd384:10'd192)+{out_index,2'b00}+bias_issue) : {1'b0,term};
    assign pool3_read_enable=issue && !fc2;
    assign pool3_byte_address={chunk,term};
    cnn_mac mac(.clk(clk),.resetn(resetn && state!=DRAIN && state!=FAULT && !abort),
        .in_valid(accepted_mac),.first(first_pipe[1]),.last(last_pipe[1]),.activation_u8(activation),
        .weight_s8(cache_data),.bias_s32(bias),.out_valid(mac_done),.accumulator_s32(mac_acc),.overflow(mac_overflow));
    assign quant_valid=good_sum && !fc2 && chunk==5;
    assign quant_acc_s32=mac_acc;
    assign logit_valid=good_sum && fc2;
    assign logit_index=out_index[4:0];
    assign logit_s32=mac_acc;
    assign diagnostic_partial_valid=good_sum;
    assign diagnostic_fc2=fc2;
    assign diagnostic_output_index=out_index;
    assign diagnostic_chunk=chunk;
    assign diagnostic_acc=mac_acc;
    assign diagnostic_hidden_valid=state==QUANT_WAIT && quant_result_valid && !stop;
    assign diagnostic_hidden=quant_result;
    assign hidden_debug_valid=result_valid && hidden_debug_index<48;
    assign hidden_debug_data=hidden_debug_valid ? hidden[hidden_debug_index] : 8'd0;
    always @(posedge clk) begin
        if (!resetn) begin
            state<=IDLE;fc2<=0;valid_result<=0;out_index<=0;chunk<=0;term<=0;bias_issue<=0;bias_return<=0;
            bias<=0;base_latched<=0;block_address<=0;drain<=0;done<=0;error<=0;error_code<=0;
            hidden_count<=0;logit_count<=0;argmax_index<=0;argmax_score<=0;hidden_valid<=0;
            hidden0<=0;hidden1<=0;hidden_pipe<=0;issue_pipe<=0;bias_pipe<=0;first_pipe<=0;last_pipe<=0;
        end else begin
            done<=0;
            issue_pipe<={issue_pipe[0],issue};bias_pipe<={bias_pipe[0],bias_read};
            first_pipe<={first_pipe[0],issue && chunk==0 && term==0};last_pipe<={last_pipe[0],issue && last_term};
            hidden_pipe<={hidden_pipe[0],issue && fc2};
            if (issue && fc2 && term<48) hidden0<=hidden[term[5:0]];
            hidden1<=hidden0;
            if (abort || clear || error) valid_result<=0;
            if (clear && state==FAULT && cache_quiescent) begin state<=IDLE;error<=0;error_code<=0;end
            if (busy && state!=DRAIN && (abort || cache_error || bad_response || bad_value || bad_hidden || mac_overflow)) begin
                error<=1;error_code<=abort?4'd1:cache_error?4'd2:bad_response?4'd3:bad_hidden?4'd7:bad_value?4'd4:4'd5;
                state<=DRAIN;drain<=0;
            end else case(state)
                IDLE: if (start && !abort && !error) begin
                    valid_result<=0;hidden_valid<=0;hidden_count<=0;logit_count<=0;argmax_index<=0;argmax_score<=0;
                    if (weight_base[2:0]!=0 || weight_base>32'hfffd6ae0) begin error<=1;error_code<=6;state<=FAULT;end
                    else begin
                        base_latched<=weight_base;block_address<=weight_base+20736;fc2<=0;out_index<=0;chunk<=0;
                        bias_issue<=0;bias_return<=0;state<=BIAS;
                    end
                end
                BIAS: begin
                    if (bias_issue==3) state<=BIAS_WAIT;else bias_issue<=bias_issue+1'b1;
                    if (cache_valid) begin bias[bias_return*8+:8]<=cache_data;bias_return<=bias_return+1'b1;end
                end
                BIAS_WAIT: if (cache_valid) begin
                    bias[bias_return*8+:8]<=cache_data;
                    if (bias_return==3) state<=LOAD;else bias_return<=bias_return+1'b1;
                end
                LOAD: if (cache_load_ready) state<=LOAD_WAIT;
                LOAD_WAIT: if (cache_loaded) begin term<=0;state<=ISSUE;end
                ISSUE: if (last_term) state<=MAC_WAIT;else term<=term+1'b1;
                MAC_WAIT: if (mac_done) begin
                    if (fc2) begin
                        logit_count<=logit_count+1'b1;
                        // Strict signed > retains the earliest index on ties, even if all scores < 0.
                        if (out_index==0 || $signed(mac_acc)>$signed(argmax_score)) begin argmax_index<=out_index[4:0];argmax_score<=mac_acc;end
                        if (out_index==21) begin state<=DRAIN;drain<=0;end else state<=NEXT;
                    end else if (chunk==5) state<=QUANT_WAIT;
                    else begin chunk<=chunk+1'b1;block_address<=block_address+512;state<=LOAD;end
                end
                QUANT_WAIT: if (quant_result_valid) begin
                    hidden[out_index]<=quant_result;hidden_valid[out_index]<=1;hidden_count<=hidden_count+1'b1;state<=NEXT;
                end
                NEXT: begin
                    chunk<=0;bias_issue<=0;bias_return<=0;state<=BIAS;
                    if (!fc2 && out_index==47) begin fc2<=1;out_index<=0;block_address<=base_latched+168192;end
                    else begin out_index<=out_index+1'b1;block_address<=block_address+(fc2?48:512);end
                end
                DRAIN: begin
                    if (!error && (abort || cache_error)) begin error<=1;error_code<=abort?4'd1:4'd2;end
                    if (drain!=16) drain<=drain+1'b1;
                    else if (cache_quiescent) begin
                        if (error || abort || cache_error) state<=FAULT;
                        else begin state<=IDLE;done<=1;valid_result<=1;end
                    end
                end
                default: ;
            endcase
        end
    end
endmodule
