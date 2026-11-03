`timescale 1ns/1ps
// 五级valid流水：完整INT32累加后Q30缩放，半值远离零，再ReLU及饱和。
module cnn_quantize (
    input wire clk, input wire resetn, input wire in_valid,
    input wire signed [31:0] acc_s32, input wire [31:0] multiplier_q30,
    output reg out_valid, output reg [7:0] activation_u8
);
    reg [3:0] valid_pipe;
    reg signed [63:0] product_s64;
    reg [63:0] magnitude_u64, rounded_u64;
    reg sign_magnitude, sign_rounded;
    reg signed [63:0] restored_s64;
    always @(posedge clk) begin
        if (!resetn) begin
            valid_pipe<=0; out_valid<=0; activation_u8<=0;
            product_s64<=0; magnitude_u64<=0; rounded_u64<=0;
            sign_magnitude<=0; sign_rounded<=0; restored_s64<=0;
        end else begin
            valid_pipe<={valid_pipe[2:0],in_valid};
            out_valid<=valid_pipe[3];
            if (in_valid)
                product_s64 <= $signed(acc_s32) * $signed({1'b0,multiplier_q30});
            if (valid_pipe[0]) begin
                sign_magnitude<=product_s64[63];
                magnitude_u64<=product_s64[63] ? (~$unsigned(product_s64)+64'd1) : $unsigned(product_s64);
            end
            if (valid_pipe[1]) begin
                rounded_u64<=(magnitude_u64+64'd536870912)>>30;
                sign_rounded<=sign_magnitude;
            end
            if (valid_pipe[2]) restored_s64<=sign_rounded ? -$signed(rounded_u64) : $signed(rounded_u64);
            if (valid_pipe[3]) begin
                if (restored_s64<=64'sd0) activation_u8<=0;
                else if (restored_s64>=64'sd127) activation_u8<=8'd127;
                else activation_u8<=restored_s64[7:0];
            end
        end
    end
endmodule
