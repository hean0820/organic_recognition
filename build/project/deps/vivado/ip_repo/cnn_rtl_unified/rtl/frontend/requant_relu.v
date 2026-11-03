`timescale 1ns/1ps
// 集成派生版：复位在计算时钟边沿生效，避免异步控制驱动RAM/DSP。
//=============================================================================
//  模块名  : requant_relu
//  功能    : INT32 累加值按 Q30 缩放，四舍五入（中点远离零），ReLU 后饱和。
//  参数    : Conv1 multiplier=3561711，Conv2 multiplier=3526514。
//  流水线 : 乘法 -> 绝对值 -> 舍入/移位 -> 恢复符号 -> ReLU/饱和。
//            从 in_valid 对应的输入采样到 out_valid 共五拍。
//=============================================================================

module requant_relu #(

        parameter integer       ACC_BITS = 32                   ,
        parameter integer       Q_BITS   = 30                   ,
        parameter integer       OUT_MAX  = 127
) (
        input                   clk                             ,
        input                   rst_n                           ,

        input                   in_valid                        ,
        input signed [ACC_BITS-1:0] acc_in                      ,
        input       [2:0]       state                           ,

        output reg  [7:0]       act_out                         ,
        output reg              out_valid
);


    localparam integer PROD_BITS = ACC_BITS + 32                 ;

    localparam signed [PROD_BITS-1:0] ROUND_BIAS =
        ({{(PROD_BITS-1){1'b0}}, 1'b1} << (Q_BITS - 1))           ;

    localparam signed [PROD_BITS-1:0] SAT_MIN = 0                 ;
    localparam signed [PROD_BITS-1:0] SAT_MAX = OUT_MAX           ;

    wire        [31:0]      multiplier                          ;

    assign multiplier = (state == 3'b001) ? 32'd3561711
                      : (state == 3'b010) ? 32'd3526514
                      : 32'd0                                   ;


    reg signed  [PROD_BITS-1:0] product_r                        ;
    reg signed  [PROD_BITS-1:0] abs_product_r                    ;
    reg signed  [PROD_BITS-1:0] abs_shifted_w                    ;
    reg signed  [PROD_BITS-1:0] rounded_w                        ;

    reg                     product_sign_r                      ;
    reg                     shifted_sign_r                      ;

    reg                     s1_valid_r                          ;
    reg                     s2_valid_r                          ;
    reg                     s3_valid_r                          ;
    reg                     s4_valid_r                          ;


    //-------------------------------------------------------------------------
    //  第一级：有符号 ACC 乘以无符号 Q30 系数。
    //  系数最高位补 0 后再转为 signed，避免被解释成负数。
    //-------------------------------------------------------------------------

    always @(posedge clk) begin
        if (!rst_n) begin
            product_r  <= 0                                     ;
            s1_valid_r <= 1'b0                                 ;
        end
        else begin
            s1_valid_r <= in_valid                              ;

            if (in_valid) begin
                product_r <= $signed(acc_in)
                           * $signed({1'b0, multiplier})        ;
            end
        end
    end


    //-------------------------------------------------------------------------
    //  第二级：保存绝对值及符号；符号必须与数据同步延迟。
    //-------------------------------------------------------------------------

    always @(posedge clk) begin
        if (!rst_n) begin
            abs_product_r  <= 0                                 ;
            product_sign_r <= 1'b0                             ;
            s2_valid_r     <= 1'b0                             ;
        end
        else begin
            s2_valid_r <= s1_valid_r                            ;

            if (s1_valid_r) begin
                product_sign_r <= product_r[PROD_BITS-1]        ;

                if (product_r[PROD_BITS-1]) begin
                    abs_product_r <= -product_r                 ;
                end
                else begin
                    abs_product_r <= product_r                  ;
                end
            end
        end
    end


    //-------------------------------------------------------------------------
    //  第三级：绝对值加 2^(Q_BITS-1) 后右移，得到中点远离零的舍入。
    //  这里不能套用 numpy.round 的“中点取偶数”规则。
    //-------------------------------------------------------------------------

    always @(posedge clk) begin
        if (!rst_n) begin
            abs_shifted_w  <= 0                                 ;
            shifted_sign_r <= 1'b0                             ;
            s3_valid_r     <= 1'b0                             ;
        end
        else begin
            s3_valid_r <= s2_valid_r                            ;

            if (s2_valid_r) begin
                abs_shifted_w  <= (abs_product_r + ROUND_BIAS) >>> Q_BITS;
                shifted_sign_r <= product_sign_r                ;
            end
        end
    end


    //-------------------------------------------------------------------------
    //  第四级：恢复有符号的 Q30 舍入结果。
    //-------------------------------------------------------------------------

    always @(posedge clk) begin
        if (!rst_n) begin
            rounded_w  <= 0                                     ;
            s4_valid_r <= 1'b0                                 ;
        end
        else begin
            s4_valid_r <= s3_valid_r                            ;

            if (s3_valid_r) begin
                if (shifted_sign_r) begin
                    rounded_w <= -abs_shifted_w                  ;
                end
                else begin
                    rounded_w <= abs_shifted_w                   ;
                end
            end
        end
    end


    //-------------------------------------------------------------------------
    //  第五级：ReLU 和上限饱和，数据与 out_valid 同拍输出。
    //-------------------------------------------------------------------------

    always @(posedge clk) begin
        if (!rst_n) begin
            act_out   <= 8'd0                                  ;
            out_valid <= 1'b0                                 ;
        end
        else begin
            out_valid <= s4_valid_r                             ;

            if (s4_valid_r) begin
                if (rounded_w <= SAT_MIN) begin
                    act_out <= 8'd0                             ;
                end
                else if (rounded_w >= SAT_MAX) begin
                    act_out <= OUT_MAX[7:0]                     ;
                end
                else begin
                    act_out <= rounded_w[7:0]                   ;
                end
            end
        end
    end

endmodule
