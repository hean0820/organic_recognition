`timescale 1ns/1ps
// 1024B：0..511权重、512..1023偏置。64位整拍写/8位读，小端字节顺序。
// 只复位输出和valid，不复位RAM内容；调用方必须维护装载有效范围。
module cnn_model_cache (
    input wire clk, input wire resetn,
    input wire write_enable, input wire [6:0] write_word_address, input wire [63:0] write_data,
    input wire read_enable, input wire [9:0] read_byte_address,
    output wire [7:0] read_data, output wire read_valid
);
    reg [1:0] valid_pipe;
    always @(posedge clk) begin
        if (!resetn) valid_pipe<=0;
        else valid_pipe<={valid_pipe[0],read_enable};
    end
    assign read_valid=valid_pipe[1];
    xpm_memory_sdpram #(
        .ADDR_WIDTH_A(7), .ADDR_WIDTH_B(10), .MEMORY_SIZE(8192),
        .WRITE_DATA_WIDTH_A(64), .BYTE_WRITE_WIDTH_A(64), .READ_DATA_WIDTH_B(8),
        .READ_LATENCY_B(2), .MEMORY_PRIMITIVE("block"), .CLOCKING_MODE("common_clock"),
        .WRITE_MODE_B("no_change"), .MEMORY_INIT_FILE("none"), .USE_MEM_INIT(0),
        .SIM_ASSERT_CHK(1), .ECC_MODE("no_ecc"), .RST_MODE_B("SYNC")
    ) memory (
        .clka(clk), .clkb(clk), .ena(write_enable), .wea(write_enable),
        .addra(write_word_address), .dina(write_data), .enb(read_enable),
        .addrb(read_byte_address), .doutb(read_data), .rstb(!resetn), .regceb(1'b1),
        .sleep(1'b0), .injectsbiterra(1'b0), .injectdbiterra(1'b0), .sbiterrb(), .dbiterrb()
    );
endmodule
