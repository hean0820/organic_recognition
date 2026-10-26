`timescale 1ns/1ps
// 输入4096B，PS A口32位读写，前端B口逐字节读。两口固定2拍读延迟。
module cnn_input_store (
    input wire clk, input wire resetn,
    input wire cpu_write, input wire cpu_read, input wire [9:0] cpu_word_address,
    input wire [31:0] cpu_write_data, output wire [31:0] cpu_read_data, output wire cpu_read_valid,
    input wire core_read, input wire [11:0] core_byte_address,
    output wire [7:0] core_read_data, output wire core_read_valid
);
    reg [1:0] cpu_valid_pipe, core_valid_pipe;
    always @(posedge clk) begin
        if (!resetn) begin cpu_valid_pipe<=0;core_valid_pipe<=0;end
        else begin cpu_valid_pipe<={cpu_valid_pipe[0],cpu_read};core_valid_pipe<={core_valid_pipe[0],core_read};end
    end
    assign cpu_read_valid=cpu_valid_pipe[1];
    assign core_read_valid=core_valid_pipe[1];
    xpm_memory_tdpram #(
        .ADDR_WIDTH_A(10), .ADDR_WIDTH_B(12), .MEMORY_SIZE(32768),
        .WRITE_DATA_WIDTH_A(32), .BYTE_WRITE_WIDTH_A(32), .READ_DATA_WIDTH_A(32),
        .WRITE_DATA_WIDTH_B(8), .BYTE_WRITE_WIDTH_B(8), .READ_DATA_WIDTH_B(8),
        .READ_LATENCY_A(2), .READ_LATENCY_B(2), .MEMORY_PRIMITIVE("block"),
        .CLOCKING_MODE("common_clock"), .WRITE_MODE_A("no_change"), .WRITE_MODE_B("no_change"),
        .MEMORY_INIT_FILE("none"), .USE_MEM_INIT(0), .SIM_ASSERT_CHK(1),
        .ECC_MODE("no_ecc"), .RST_MODE_A("SYNC"), .RST_MODE_B("SYNC")
    ) memory (
        .clka(clk), .rsta(!resetn), .ena(cpu_write||cpu_read), .regcea(1'b1), .wea(cpu_write),
        .addra(cpu_word_address), .dina(cpu_write_data), .douta(cpu_read_data),
        .clkb(clk), .rstb(!resetn), .enb(core_read), .regceb(1'b1), .web(1'b0),
        .addrb(core_byte_address), .dinb(8'd0), .doutb(core_read_data),
        .sleep(1'b0), .injectsbiterra(1'b0), .injectdbiterra(1'b0),
        .injectsbiterrb(1'b0), .injectdbiterrb(1'b0), .sbiterra(), .dbiterra(), .sbiterrb(), .dbiterrb()
    );
endmodule
