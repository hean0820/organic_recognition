`timescale 1ns/1ps
// Capacity and word read port match the old 12KiB Pool2 output RAM.
// The adapter selects the delayed byte lane from a two-register 32-bit read.
module cnn_pool2_store (
    input wire clk, resetn, owner_conv3,
    input wire write_enable, input wire [13:0] write_address, input wire [7:0] write_data,
    input wire read_enable, input wire [13:0] read_address,
    output wire [7:0] read_data, output wire read_valid, output wire rejected_write
);
    wire accept_read=read_enable && owner_conv3 && read_address<12288;
    wire [31:0] bank_data[0:2];
    reg [1:0] valid_pipe;
    reg [1:0] lane0,lane1;
    reg [1:0] bank0,bank1;
    wire [31:0] word_data=bank_data[bank1];
    assign rejected_write=write_enable && (owner_conv3 || write_address>=12288);
    assign read_valid=valid_pipe[1];
    assign read_data=word_data[lane1*8+:8];
    always @(posedge clk) begin
        if (!resetn) begin valid_pipe<=0; lane0<=0; lane1<=0; bank0<=0; bank1<=0; end
        else begin
            valid_pipe<={valid_pipe[0],accept_read}; lane0<=read_address[1:0]; lane1<=lane0;
            bank0<=read_address[13:12]; bank1<=bank0;
        end
    end
    // Three power-of-two banks avoid XPM's 12KiB -> 16KiB padding (4 tiles).
    genvar b;
    generate for (b=0;b<3;b=b+1) begin: banks
    wire bank_write=write_enable && !rejected_write && write_address[13:12]==b;
    xpm_memory_sdpram #(
        .ADDR_WIDTH_A(12),.ADDR_WIDTH_B(10),.MEMORY_SIZE(32768),
        .WRITE_DATA_WIDTH_A(8),.BYTE_WRITE_WIDTH_A(8),.READ_DATA_WIDTH_B(32),
        .READ_LATENCY_B(2),.MEMORY_PRIMITIVE("block"),.CLOCKING_MODE("common_clock"),
        .WRITE_MODE_B("no_change"),.MEMORY_INIT_FILE("none"),.USE_MEM_INIT(0),
        .SIM_ASSERT_CHK(1),.ECC_MODE("no_ecc"),.RST_MODE_B("SYNC")
    ) memory (.clka(clk),.clkb(clk),.ena(bank_write),.wea(bank_write),
        .addra(write_address[11:0]),.dina(write_data),.enb(accept_read && read_address[13:12]==b),.addrb(read_address[11:2]),
        .doutb(bank_data[b]),.rstb(!resetn),.regceb(1'b1),.sleep(1'b0),
        .injectsbiterra(1'b0),.injectdbiterra(1'b0),.sbiterrb(),.dbiterrb());
    end endgenerate
endmodule

module cnn_pool3_store (
    input wire clk, resetn,
    input wire write_enable, input wire [11:0] write_address, input wire [7:0] write_data,
    input wire read_enable, input wire [11:0] read_address,
    output wire [7:0] read_data, output wire read_valid
);
    reg [1:0] valid_pipe;
    always @(posedge clk) begin
        if (!resetn) valid_pipe<=0;
        else valid_pipe<={valid_pipe[0],read_enable && read_address<3072};
    end
    assign read_valid=valid_pipe[1];
    xpm_memory_sdpram #(
        .ADDR_WIDTH_A(12),.ADDR_WIDTH_B(12),.MEMORY_SIZE(24576),
        .WRITE_DATA_WIDTH_A(8),.BYTE_WRITE_WIDTH_A(8),.READ_DATA_WIDTH_B(8),
        .READ_LATENCY_B(2),.MEMORY_PRIMITIVE("block"),.CLOCKING_MODE("common_clock"),
        .WRITE_MODE_B("no_change"),.MEMORY_INIT_FILE("none"),.USE_MEM_INIT(0),
        .SIM_ASSERT_CHK(1),.ECC_MODE("no_ecc"),.RST_MODE_B("SYNC")
    ) memory (.clka(clk),.clkb(clk),.ena(write_enable && write_address<3072),
        .wea(write_enable && write_address<3072),.addra(write_address),.dina(write_data),
        .enb(read_enable && read_address<3072),.addrb(read_address),.doutb(read_data),
        .rstb(!resetn),.regceb(1'b1),.sleep(1'b0),.injectsbiterra(1'b0),
        .injectdbiterra(1'b0),.sbiterrb(),.dbiterrb());
endmodule
