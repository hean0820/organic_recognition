`timescale 1ns/1ps
// Candidate: 2/4 output-channel lanes, each preserving scalar IC/KY/KX order.
// One Pool2 byte is broadcast; 432 x 32-bit local weights supply four OCs.
// Original 432B DDR blocks, bias cache, external ports and quantizer are retained.
module cnn_conv3_pool3 #(
    parameter integer LANES = 4
) (
    input wire clk, resetn, start, clear, abort,
    input wire [31:0] weight_base,
    output wire busy, output reg done, error,
    output reg [3:0] error_code,
    output wire pool2_read_enable, output wire [13:0] pool2_byte_address,
    input wire [7:0] pool2_data, input wire pool2_valid,
    output wire cache_load_valid, input wire cache_load_ready,
    output wire [31:0] cache_load_address, output wire [15:0] cache_load_bytes,
    input wire cache_loaded, cache_error, cache_quiescent,
    output wire cache_read_enable, output wire [9:0] cache_read_address,
    input wire [7:0] cache_data, input wire cache_valid,
    output wire quant_valid, output wire signed [31:0] quant_acc_s32,
    input wire quant_result_valid, input wire [7:0] quant_result,
    output wire pool3_write_enable, output wire [11:0] pool3_byte_address,
    output wire [7:0] pool3_data, output reg [31:0] pool3_count,
    output wire diagnostic_acc_valid, output wire [13:0] diagnostic_address,
    output wire signed [31:0] diagnostic_acc,
    output wire diagnostic_activation_valid, output wire [7:0] diagnostic_activation
);
    // Keep original principal state codes for existing integration fault tests.
    localparam IDLE=0, LOAD=1, LOAD_WAIT=2, BIAS=3, BIAS_WAIT=4,
               ISSUE=5, MAC_WAIT=6, QUANT_WAIT=7, COMMIT=8, DRAIN=9,
               FAULT=10, COPY=11, COPY_WAIT=12, QUANT_START=13;
    reg [3:0] state;
    reg [5:0] oc, ic;
    reg [2:0] py, px;
    reg [1:0] subpixel, ky, kx, bias_issue, bias_return;
    reg [1:0] load_lane, quant_lane;
    reg [8:0] term, copy_term, copy_address0, copy_address1;
    reg [31:0] block_address;
    reg signed [31:0] bias [0:LANES-1];
    reg [7:0] pool_max [0:LANES-1];
    reg [4:0] drain_count;
    reg [1:0] issue_pipe, first_pipe, last_pipe, pad_pipe, copy_pipe;
    wire stop = abort || error || cache_error;
    wire issue = state==ISSUE && !stop;
    wire copying = state==COPY && !stop;
    wire bias_read = state==BIAS && !stop;
    wire [5:0] load_oc = oc + load_lane;
    wire [5:0] result_oc = oc + quant_lane;
    wire signed [5:0] iy = $signed({1'b0,py,subpixel[1]}) + $signed({4'b0,ky}) - 6'sd1;
    wire signed [5:0] ix = $signed({1'b0,px,subpixel[0]}) + $signed({4'b0,kx}) - 6'sd1;
    wire padding = iy<0 || iy>15 || ix<0 || ix>15;
    wire arithmetic_resetn = resetn && state!=DRAIN && state!=FAULT && !abort;
    wire mac_valid = issue_pipe[1] && !stop;
    wire bad_response = (issue_pipe[1] && !pad_pipe[1] && !pool2_valid)
                      || (copy_pipe[1] && !cache_valid);
    wire bad_value = (mac_valid && !pad_pipe[1] && pool2_data>127)
                   || (copy_pipe[1] && cache_valid && cache_data==8'h80);
    wire [LANES-1:0] mac_done, mac_overflow;
    wire signed [31:0] mac_acc [0:LANES-1];
    wire [31:0] local_weights;
    wire local_write = copy_pipe[1] && cache_valid && !stop && !bad_value;
    wire [3:0] local_we = local_write ? (4'b0001 << load_lane) : 4'b0000;

    // Interleaved OC bytes in a single small BRAM; no Pool2 replication.
    xpm_memory_sdpram #(
        .ADDR_WIDTH_A(9), .ADDR_WIDTH_B(9), .MEMORY_SIZE(16384),
        .WRITE_DATA_WIDTH_A(32), .BYTE_WRITE_WIDTH_A(8), .READ_DATA_WIDTH_B(32),
        .READ_LATENCY_B(2), .MEMORY_PRIMITIVE("block"), .CLOCKING_MODE("common_clock"),
        .WRITE_MODE_B("no_change"), .MEMORY_INIT_FILE("none"), .USE_MEM_INIT(0),
        .SIM_ASSERT_CHK(1), .ECC_MODE("no_ecc"), .RST_MODE_B("SYNC")
    ) weights (.clka(clk), .clkb(clk), .ena(local_write), .wea(local_we),
        .addra(copy_address1), .dina({4{cache_data}}),
        .enb(issue), .addrb(term), .doutb(local_weights),
        .rstb(!resetn), .regceb(1'b1), .sleep(1'b0),
        .injectsbiterra(1'b0), .injectdbiterra(1'b0), .sbiterrb(), .dbiterrb());

    genvar lane;
    generate for (lane=0; lane<LANES; lane=lane+1) begin: lanes
        cnn_mac mac (.clk(clk), .resetn(arithmetic_resetn),
            .in_valid(mac_valid && !bad_response && !bad_value),
            .first(first_pipe[1]), .last(last_pipe[1]),
            .activation_u8(pad_pipe[1] ? 8'd0 : pool2_data),
            .weight_s8(local_weights[lane*8+:8]), .bias_s32(bias[lane]),
            .out_valid(mac_done[lane]), .accumulator_s32(mac_acc[lane]),
            .overflow(mac_overflow[lane]));
    end endgenerate

    assign busy = state!=IDLE && state!=FAULT;
    assign cache_load_valid = state==LOAD && !stop;
    assign cache_load_address = block_address;
    assign cache_load_bytes = 16'd432;
    assign cache_read_enable = copying || bias_read;
    assign cache_read_address = bias_read ?
        (10'd512 + {load_oc,2'b00} + bias_issue) : {1'b0,copy_term};
    assign pool2_read_enable = issue && !padding;
    assign pool2_byte_address = padding ? 14'd0 : {ic,iy[3:0],ix[3:0]};
    assign quant_valid = state==QUANT_START && !stop;
    assign quant_acc_s32 = mac_acc[quant_lane];
    assign diagnostic_acc_valid = quant_valid;
    assign diagnostic_acc = quant_acc_s32;
    assign diagnostic_address = {result_oc,py,subpixel[1],px,subpixel[0]};
    assign diagnostic_activation_valid = state==QUANT_WAIT && quant_result_valid && !stop;
    assign diagnostic_activation = quant_result;
    assign pool3_write_enable = state==COMMIT && !stop;
    assign pool3_byte_address = {result_oc,py,px};
    assign pool3_data = pool_max[quant_lane];

    integer k;
    initial begin
        if (LANES!=2 && LANES!=4) $error("Conv3 supports LANES=2 or 4");
    end
    always @(posedge clk) begin
        if (!resetn) begin
            state<=IDLE; done<=0; error<=0; error_code<=0; pool3_count<=0;
            oc<=0; ic<=0; py<=0; px<=0; subpixel<=0; ky<=0; kx<=0;
            term<=0; copy_term<=0; copy_address0<=0; copy_address1<=0;
            block_address<=0; load_lane<=0; quant_lane<=0;
            bias_issue<=0; bias_return<=0; drain_count<=0;
            issue_pipe<=0; first_pipe<=0; last_pipe<=0; pad_pipe<=0; copy_pipe<=0;
            for (k=0;k<LANES;k=k+1) begin bias[k]<=0; pool_max[k]<=0; end
        end else begin
            done<=0;
            issue_pipe<={issue_pipe[0],issue};
            first_pipe<={first_pipe[0],issue && term==0};
            last_pipe<={last_pipe[0],issue && term==431};
            pad_pipe<={pad_pipe[0],padding};
            copy_pipe<={copy_pipe[0],copying};
            copy_address0<=copy_term; copy_address1<=copy_address0;
            if (clear && state==FAULT && cache_quiescent) begin
                state<=IDLE; error<=0; error_code<=0;
            end
            if (state!=IDLE && state!=FAULT && state!=DRAIN &&
                (abort || cache_error || bad_response || bad_value || (|mac_overflow))) begin
                state<=DRAIN; drain_count<=0; error<=1;
                error_code<=abort ? 4'd1 : cache_error ? 4'd2 : bad_response ? 4'd3 : bad_value ? 4'd4 : 4'd5;
            end else case (state)
                IDLE: if (start && !abort && !error) begin
                    if (weight_base[2:0]!=0 || weight_base>32'hffffaf00) begin
                        error<=1; error_code<=6; state<=FAULT;
                    end else begin
                        state<=LOAD; block_address<=weight_base; oc<=0; py<=0; px<=0;
                        load_lane<=0; quant_lane<=0; subpixel<=0; pool3_count<=0;
                    end
                end
                LOAD: if (cache_load_ready) state<=LOAD_WAIT;
                LOAD_WAIT: if (cache_loaded) begin
                    state<=BIAS; bias_issue<=0; bias_return<=0;
                end
                BIAS: begin
                    if (bias_issue==3) state<=BIAS_WAIT; else bias_issue<=bias_issue+1'b1;
                    if (cache_valid) begin
                        bias[load_lane][bias_return*8+:8]<=cache_data;
                        bias_return<=bias_return+1'b1;
                    end
                end
                BIAS_WAIT: if (cache_valid) begin
                    bias[load_lane][bias_return*8+:8]<=cache_data;
                    if (bias_return==3) begin state<=COPY; copy_term<=0; end
                    else bias_return<=bias_return+1'b1;
                end
                COPY: begin
                    if (copy_term==431) state<=COPY_WAIT;
                    else copy_term<=copy_term+1'b1;
                end
                COPY_WAIT: if (copy_pipe[1] && cache_valid && copy_address1==431) begin
                    if (load_lane==LANES-1) begin
                        state<=ISSUE; term<=0; ic<=0; ky<=0; kx<=0;
                    end else begin
                        load_lane<=load_lane+1'b1;
                        block_address<=block_address+432; state<=LOAD;
                    end
                end
                ISSUE: begin
                    if (term==431) state<=MAC_WAIT;
                    else begin
                        term<=term+1'b1;
                        if (kx==2) begin
                            kx<=0;
                            if (ky==2) begin ky<=0; ic<=ic+1'b1; end
                            else ky<=ky+1'b1;
                        end else kx<=kx+1'b1;
                    end
                end
                MAC_WAIT: if (&mac_done) begin quant_lane<=0; state<=QUANT_START; end
                QUANT_START: state<=QUANT_WAIT;
                QUANT_WAIT: if (quant_result_valid) begin
                    if (subpixel==0 || quant_result>pool_max[quant_lane])
                        pool_max[quant_lane]<=quant_result;
                    if (quant_lane!=LANES-1) begin
                        quant_lane<=quant_lane+1'b1; state<=QUANT_START;
                    end else begin
                        quant_lane<=0;
                        if (subpixel==3) state<=COMMIT;
                        else begin
                            subpixel<=subpixel+1'b1;
                            term<=0; ic<=0; ky<=0; kx<=0; state<=ISSUE;
                        end
                    end
                end
                COMMIT: begin
                    pool3_count<=pool3_count+1'b1;
                    if (quant_lane!=LANES-1) quant_lane<=quant_lane+1'b1;
                    else begin
                        quant_lane<=0; subpixel<=0; term<=0; ic<=0; ky<=0; kx<=0;
                        if (px!=7) begin px<=px+1'b1; state<=ISSUE; end
                        else if (py!=7) begin px<=0; py<=py+1'b1; state<=ISSUE; end
                        else if (oc!=48-LANES) begin
                            px<=0; py<=0; oc<=oc+LANES; load_lane<=0;
                            block_address<=block_address+432; state<=LOAD;
                        end else begin state<=DRAIN; drain_count<=0; end
                    end
                end
                DRAIN: begin
                    if (!error && (abort || cache_error)) begin
                        error<=1; error_code<=abort ? 4'd1 : 4'd2;
                    end
                    if (drain_count!=16) drain_count<=drain_count+1'b1;
                    else if (cache_quiescent) begin
                        if (error || abort || cache_error) state<=FAULT;
                        else begin state<=IDLE; done<=1; end
                    end
                end
                default: ;
            endcase
        end
    end
endmodule
