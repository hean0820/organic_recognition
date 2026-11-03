`timescale 1ns/1ps
`include "s2_vector_paths.vh"
// 仅仿真DDR从机：随机延迟/背压以及可控响应错误，不参与综合。
module axi_read_memory_model #(parameter USE_MODEL_FILES=0)(
    input wire clk,input wire resetn,input wire hold_ar,input wire hold_r,
    input wire [3:0] fault_mode,input wire inject_unsolicited,
    input wire [31:0] araddr,input wire [7:0] arlen,input wire [2:0] arsize,input wire [1:0] arburst,
    input wire arvalid,output wire arready,
    output reg rid,output reg [63:0] rdata,output reg [1:0] rresp,output reg rlast,output reg rvalid,input wire rready
);
    reg [31:0] lfsr,base;
    reg [7:0] length,index;
    reg [3:0] fault;
    reg sending;
    reg [7:0] weights[0:169247];
    reg [7:0] biases[0:471];
    integer j;
    initial if(USE_MODEL_FILES)begin $readmemh(`WEIGHTS_FILE,weights);$readmemh(`BIAS_FILE,biases);end
    function [7:0] byte_at(input [31:0] address);
        if(USE_MODEL_FILES && address>=32'h01000000 && address<32'h01029520)byte_at=weights[address-32'h01000000];
        else if(USE_MODEL_FILES && address>=32'h02000000 && address<32'h020001d8)byte_at=biases[address-32'h02000000];
        else byte_at=((address*13)^(address>>8)^32'h5a)&255;
    endfunction
    assign arready=resetn && !hold_ar && !sending && !rvalid && lfsr[1:0]!=0;
    always @(posedge clk)begin
        if(!resetn)begin lfsr<=32'h54183621;base<=0;length<=0;index<=0;fault<=0;sending<=0;
            rid<=0;rdata<=0;rresp<=0;rlast<=0;rvalid<=0;end
        else begin
            lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
            if(arvalid&&arready)begin
                if(araddr[2:0]!=0||arlen>15||arsize!=3||arburst!=1||
                    (araddr>>12)!=((araddr+((arlen+1)*8)-1)>>12))$fatal(1,"invalid AXI burst");
                base<=araddr;length<=arlen;index<=0;fault<=fault_mode;sending<=1;
            end
            if(rvalid&&rready)begin
                rvalid<=0;
                if(index==length+(fault==5?1:0))sending<=0;
                else index<=index+1'b1;
            end
            if(sending&&!rvalid&&!hold_r&&lfsr[3:2]!=0)begin
                for(j=0;j<8;j=j+1)rdata[j*8+:8]<=byte_at(base+index*8+j);
                rresp<=(fault==1&&index==1)?2'b10:0;
                rid<=(fault==2&&index==1);
                rlast<=fault==3 ? (index==0||index==length) : fault==4 ? 1'b0 : fault==5 ? (index==length+1) : (index==length);
                rvalid<=1;
            end
            if(inject_unsolicited&&!sending&&!rvalid)begin
                rdata<=64'h1234567812345678;rresp<=0;rid<=0;rlast<=1;rvalid<=1;
            end
        end
    end
endmodule
