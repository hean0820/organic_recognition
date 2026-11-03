`include "s5_paths.vh"
`include "s2_vector_paths.vh"
    reg clk=0;always #5 clk=~clk;reg resetn=0;
    reg[15:0]awaddr=0,araddr=0;reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    reg[31:0]wdata=0;reg[3:0]wstrb=15;wire awready,wready,bvalid,arready,rvalid;wire[1:0]bresp,rresp;wire[31:0]rdata;
    wire[31:0]ma;wire[7:0]ml;wire mid,mlock,mvalid,mready,rid,rlast,mrvalid,mrready;
    wire[2:0]msize,mprot;wire[1:0]mburst,mresp;wire[3:0]mcache,mqos;wire[63:0]mrdata;
    reg hold_ar=0,hold_r=0,inject=0;reg[3:0]fault=0;
    cnn_rtl_unified dut(.clk(clk),.resetn(resetn),.s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),.s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
        .m_axi_araddr(ma),.m_axi_arlen(ml),.m_axi_arid(mid),.m_axi_arsize(msize),.m_axi_arburst(mburst),.m_axi_arlock(mlock),.m_axi_arcache(mcache),.m_axi_arprot(mprot),.m_axi_arqos(mqos),
        .m_axi_arvalid(mvalid),.m_axi_arready(mready),.m_axi_rid(rid),.m_axi_rdata(mrdata),.m_axi_rresp(mresp),.m_axi_rlast(rlast),.m_axi_rvalid(mrvalid),.m_axi_rready(mrready));
    axi_read_memory_model #(.USE_MODEL_FILES(1))memory(.clk(clk),.resetn(resetn),.hold_ar(hold_ar),.hold_r(hold_r),.fault_mode(fault),.inject_unsolicited(inject),
        .araddr(ma),.arlen(ml),.arsize(msize),.arburst(mburst),.arvalid(mvalid),.arready(mready),.rid(rid),.rdata(mrdata),.rresp(mresp),.rlast(rlast),.rvalid(mrvalid),.rready(mrready));
    integer bus_waits=0,bus_writes=0,bus_reads=0;reg[31:0]value,held;reg[1:0]held_resp;
    task write_bus(input[15:0]address,input[31:0]data,input[1:0]expected);reg got_a,got_w;begin
        @(negedge clk);awaddr=address;wdata=data;awvalid=1;wvalid=1;got_a=0;got_w=0;bus_waits=0;
        while(!got_a||!got_w)begin @(posedge clk);if(awvalid&&awready)got_a=1;if(wvalid&&wready)got_w=1;
            @(negedge clk);if(got_a)awvalid=0;if(got_w)wvalid=0;bus_waits=bus_waits+1;if(bus_waits>1000)$fatal(1,"AXIL AW/W wait");end
        bus_waits=0;while(!bvalid)begin @(negedge clk);bus_waits=bus_waits+1;if(bus_waits>1000)$fatal(1,"AXIL B wait");end
        if(bresp!==expected)$fatal(1,"AXIL BRESP address=%h expected=%d got=%d control=%d",address,expected,bresp,dut.control_state);
        held_resp=bresp;repeat(2)begin @(negedge clk);if(!bvalid||bresp!==held_resp)$fatal(1,"B not stable");end
        bready=1;@(negedge clk);bready=0;bus_writes=bus_writes+1;
    end endtask
    task read_bus(input[15:0]address,input[1:0]expected,output[31:0]data);begin
        @(negedge clk);araddr=address;arvalid=1;bus_waits=0;
        begin:accept_read forever begin @(posedge clk);if(arready)disable accept_read;bus_waits=bus_waits+1;if(bus_waits>1000)$fatal(1,"AXIL AR wait");end end
        @(negedge clk);arvalid=0;bus_waits=0;
        while(!rvalid)begin @(negedge clk);bus_waits=bus_waits+1;if(bus_waits>1000)$fatal(1,"AXIL R wait address=%h",address);end
        if(rresp!==expected)$fatal(1,"AXIL RRESP address=%h got=%d expected=%d",address,rresp,expected);
        held=rdata;held_resp=rresp;repeat(2)begin @(negedge clk);if(!rvalid||rdata!==held||rresp!==held_resp)$fatal(1,"R not stable");end
        data=held;rready=1;@(negedge clk);rready=0;bus_reads=bus_reads+1;
    end endtask
    task configure;begin
        write_bus('h40,'h01000000,0);write_bus('h44,169248,0);write_bus('h48,169280,0);
        write_bus('h4c,'h02000000,0);write_bus('h50,472,0);write_bus('h54,512,0);write_bus('h58,'hb91cb580,0);
        write_bus('h5c,40000000,0);write_bus('h60,10000,0);
    end endtask
