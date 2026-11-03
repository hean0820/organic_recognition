`timescale 1ns/1ps
module tb_prep_identity;
 reg clk=0;always #5 clk=~clk;reg resetn=0;
 reg[6:0] awaddr=0,araddr=0;reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
 reg[31:0] wdata=0;wire awready,wready,bvalid,arready,rvalid;wire[31:0]rdata;wire[1:0]bresp,rresp;
 wire ma,mw,mr;
 wire [31:0] mem_awaddr,mem_araddr,mem_wdata; wire [7:0] mem_arlen,mem_awlen;
 wire [3:0] mem_wstrb; wire mem_rready,mem_wlast,mem_bready;
 reg sending=0,writing=0,response=0; reg [31:0] addr;
 reg [7:0] remaining,write_left; reg pixel_test=0;
 integer words=0, bursts=0;
 function automatic [31:0] red_pixels(input [31:0] byte_addr);
   integer j; begin
     for(j=0;j<4;j=j+1) red_pixels[j*8+:8]=((byte_addr-32'h00100000+j)%3==2)?8'hff:8'h00;
   end
 endfunction
 always @(posedge clk) begin
   if(mr&&!sending)begin
     if(!pixel_test || mem_araddr < 32'h00100000 || mem_araddr >= 32'h00400000)$fatal(1,"frame read address");
     addr<=mem_araddr;remaining<=mem_arlen;sending<=1;bursts<=bursts+1;
   end
   if(sending && mem_rready)begin
     if(remaining==0)sending<=0;else begin addr<=addr+4;remaining<=remaining-1;end
   end
   if(ma&&!writing&&!response)begin
     if(!pixel_test || mem_awaddr!==32'h00400000+4*words)$fatal(1,"detection address");
     write_left<=mem_awlen;writing<=1;
   end
   if(mw&&writing)begin
     if(mem_wdata!==32'h4c4c4c4c || mem_wstrb!==4'hf || mem_wlast!==(write_left==0))$fatal(1,"red ROI grayscale or burst mismatch");
     words<=words+1;
     if(write_left==0)begin writing<=0;response<=1;end else write_left<=write_left-1;
   end
   if(response&&mem_bready)response<=0;
 end
 prep_only_accel dut(.ap_clk(clk),.ap_rst_n(resetn),
  .s_axi_control_AWADDR(awaddr),.s_axi_control_AWVALID(awvalid),.s_axi_control_AWREADY(awready),
  .s_axi_control_WDATA(wdata),.s_axi_control_WSTRB(4'hf),.s_axi_control_WVALID(wvalid),.s_axi_control_WREADY(wready),
  .s_axi_control_BRESP(bresp),.s_axi_control_BVALID(bvalid),.s_axi_control_BREADY(bready),
  .s_axi_control_ARADDR(araddr),.s_axi_control_ARVALID(arvalid),.s_axi_control_ARREADY(arready),
  .s_axi_control_RDATA(rdata),.s_axi_control_RRESP(rresp),.s_axi_control_RVALID(rvalid),.s_axi_control_RREADY(rready),
  .m_axi_gmem_AWVALID(ma),.m_axi_gmem_AWREADY(!writing && !response),.m_axi_gmem_AWADDR(mem_awaddr),.m_axi_gmem_AWLEN(mem_awlen),.m_axi_gmem_WVALID(mw),.m_axi_gmem_WREADY(writing),.m_axi_gmem_WDATA(mem_wdata),.m_axi_gmem_WSTRB(mem_wstrb),.m_axi_gmem_WLAST(mem_wlast),
  .m_axi_gmem_ARVALID(mr),.m_axi_gmem_ARREADY(!sending),.m_axi_gmem_ARADDR(mem_araddr),.m_axi_gmem_ARLEN(mem_arlen),.m_axi_gmem_RVALID(sending),.m_axi_gmem_RDATA(red_pixels(addr)),.m_axi_gmem_RREADY(mem_rready),
  .m_axi_gmem_RLAST(remaining==0),.m_axi_gmem_RRESP(2'd0),.m_axi_gmem_RID(1'b0),.m_axi_gmem_RUSER(1'b0),
  .m_axi_gmem_BVALID(response),.m_axi_gmem_BREADY(mem_bready),.m_axi_gmem_BRESP(2'd0),.m_axi_gmem_BID(1'b0),.m_axi_gmem_BUSER(1'b0));
 always @(posedge clk)if(resetn&&!pixel_test&&(ma||mw||mr))$fatal(1,"Rejected/identity mode accessed DDR");
 task wr(input[6:0]addr,input[31:0]data);begin
  @(negedge clk);awaddr=addr;awvalid=1;
  do @(posedge clk);while(!awready);
  @(negedge clk);awvalid=0;wdata=data;wvalid=1;
  do @(posedge clk);while(!wready);
  @(negedge clk);wvalid=0;bready=1;
  do @(posedge clk);while(!bvalid);
  if(bresp!=0)$fatal(1,"Write response");
  @(negedge clk);bready=0;
 end endtask
 task rd(input[6:0]addr,output[31:0]data);begin
  @(negedge clk);araddr=addr;arvalid=1;
  do @(posedge clk);while(!arready);
  @(negedge clk);arvalid=0;rready=1;
  do @(posedge clk);while(!rvalid);
  if(rresp!=0)$fatal(1,"Read response");data=rdata;
  @(negedge clk);rready=0;
 end endtask
 reg[31:0]value;integer i,j;reg done_seen;
 initial begin
  repeat(10)@(posedge clk);@(negedge clk);resetn=1;
  repeat(10)@(posedge clk);
  // Poison pointer values: neither identity nor rejected modes may dereference them.
  wr('h18,32'hfffffff0);wr('h24,32'hfffffff0);wr('h30,32'hfffffff0);wr('h3c,32'hfffffff0);wr('h48,32'hfffffff0);
  wr('h54,960);
  for(i=0;i<4;i=i+1)begin
   wr('h5c,i==0?4:i==1?3:i==2?2:5);wr(0,1);done_seen=0;
   begin:poll_loop
    for(j=0;j<1000;j=j+1)begin
     rd(0,value);done_seen=done_seen||value[1];
     if(done_seen&&value[2]&&!value[0])disable poll_loop;
    end
    $fatal(1,"DONE/IDLE timeout mode=%0d status=%h",i,value);
   end
   rd('h10,value);if(value!=(i==0?32'h50525001:1))$fatal(1,"Identity/reject returned %h",value);
  end
  repeat(30)@(posedge clk);
  $display("S6_PREP_IDENTITY_RTL_PASS 4 calls, no AR/AW/W");
  pixel_test=1;wr('h18,32'h00100000);wr('h24,32'h00400000);wr('h30,32'h00800000);wr('h3c,32'h00c00000);wr('h48,32'h01000000);
  wr('h5c,0);wr(0,1);wait(words==160);
  if(bursts<1)$fatal(1,"no frame reads");
  $display("PREP_PIXEL_PASS red_bgr_to_gray=76 detection_pixels=640 first_row_only");$finish;
 end
 initial begin #1000000;$fatal(1,"Test timeout");end
endmodule
