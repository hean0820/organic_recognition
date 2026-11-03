// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2020.2 (64-bit)
// Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
// ==============================================================
`timescale 1 ns / 1 ps
module prep_only_accel_make_detection_rows_0_0_ram (addr0, ce0, d0, we0, q0, addr1, ce1, q1,  clk);

parameter DWIDTH = 8;
parameter AWIDTH = 9;
parameter MEM_SIZE = 480;

input[AWIDTH-1:0] addr0;
input ce0;
input[DWIDTH-1:0] d0;
input we0;
output reg[DWIDTH-1:0] q0;
input[AWIDTH-1:0] addr1;
input ce1;
output reg[DWIDTH-1:0] q1;
input clk;

reg [DWIDTH-1:0] ram0[0:MEM_SIZE-1];



always @(posedge clk)  
begin 
    if (ce0) begin
        if (we0) 
            ram0[addr0] <= d0; 
        q0 <= ram0[addr0];
    end
end


always @(posedge clk)  
begin 
    if (ce1) begin
        q1 <= ram0[addr1];
    end
end


endmodule

`timescale 1 ns / 1 ps
module prep_only_accel_make_detection_rows_0_0(
    reset,
    clk,
    address0,
    ce0,
    we0,
    d0,
    q0,
    address1,
    ce1,
    q1);

parameter DataWidth = 32'd8;
parameter AddressRange = 32'd480;
parameter AddressWidth = 32'd9;
input reset;
input clk;
input[AddressWidth - 1:0] address0;
input ce0;
input we0;
input[DataWidth - 1:0] d0;
output[DataWidth - 1:0] q0;
input[AddressWidth - 1:0] address1;
input ce1;
output[DataWidth - 1:0] q1;



prep_only_accel_make_detection_rows_0_0_ram prep_only_accel_make_detection_rows_0_0_ram_U(
    .clk( clk ),
    .addr0( address0 ),
    .ce0( ce0 ),
    .we0( we0 ),
    .d0( d0 ),
    .q0( q0 ),
    .addr1( address1 ),
    .ce1( ce1 ),
    .q1( q1 ));

endmodule

