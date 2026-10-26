`timescale 1ns/1ps
// UINT8先补零成为signed9，再乘signed8。first只加一次bias，last排在该乘积之后。
module cnn_mac (
    input wire clk, input wire resetn, input wire in_valid,
    input wire first, input wire last, input wire [7:0] activation_u8,
    input wire signed [7:0] weight_s8, input wire signed [31:0] bias_s32,
    output reg out_valid, output reg signed [31:0] accumulator_s32,
    output reg overflow
);
    reg valid_d, first_d, last_d;
    reg signed [16:0] product_s17;
    reg signed [31:0] bias_d;
    wire signed [32:0] base_s33 = first_d ? {bias_d[31],bias_d} : {accumulator_s32[31],accumulator_s32};
    wire signed [32:0] sum_s33 = base_s33 + {{16{product_s17[16]}},product_s17};
    always @(posedge clk) begin
        if (!resetn) begin
            valid_d<=0; first_d<=0; last_d<=0; product_s17<=0; bias_d<=0;
            out_valid<=0; accumulator_s32<=0; overflow<=0;
        end else begin
            valid_d<=in_valid; out_valid<=valid_d && last_d; overflow<=0;
            if (in_valid) begin
                first_d<=first; last_d<=last; bias_d<=bias_s32;
                product_s17<=$signed({1'b0,activation_u8}) * $signed(weight_s8);
            end
            if (valid_d) begin
                accumulator_s32<=sum_s33[31:0];
                overflow<=sum_s33[32]!=sum_s33[31];
            end
        end
    end
endmodule
