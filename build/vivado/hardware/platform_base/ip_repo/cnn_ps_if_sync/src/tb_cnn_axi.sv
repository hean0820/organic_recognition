`timescale 1ns/1ps
module tb_cnn_axi;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg [15:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0;
    reg [3:0] wstrb=0;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [1:0] bresp,rresp;
    wire [31:0] rdata;
    wire [7:0] image_data,real_feature;
    wire image_valid,real_ready,real_valid,real_done,core_resetn;
    reg fake_mode=0,fake_valid=0,fake_done=0;
    reg [7:0] fake_data=0;
    reg [7:0] image[0:4095],expected[0:12287];
    reg [4095:0] path,data_root="data",result_path="axi_result.txt";
    integer fd,found,frame,i,j,received,produced,polls;
    reg checking=0;
    reg [31:0] value,word,seq;
    cnn_axi_buffer #(.WATCHDOG_CYCLES(1000000)) dut (
        .clk(clk),.resetn(resetn),.awaddr(awaddr),.awvalid(awvalid),.awready(awready),
        .wdata(wdata),.wstrb(wstrb),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.araddr(araddr),.arvalid(arvalid),
        .arready(arready),.rdata(rdata),.rresp(rresp),.rvalid(rvalid),.rready(rready),
        .image_data(image_data),.image_valid(image_valid),.image_ready(fake_mode ? 1'b1:real_ready),
        .feature_data(fake_mode ? fake_data:real_feature),.feature_valid(fake_mode ? fake_valid:real_valid),
        .frame_done(fake_mode ? fake_done:real_done),.core_resetn(core_resetn)
    );
    cnn_top #(.CONV2_LANES(2)) core (.sclk(clk),.s_rst_n(core_resetn),.image_data(image_data),
        .image_data_vld(image_valid && !fake_mode),.image_data_ready(real_ready),
        .pool_data_out(real_feature),.pool_data_out_vld(real_valid),.frame_done(real_done));
    always @(posedge clk) if(resetn && checking) begin
        if(image_valid && real_ready) begin
            if(received>=4096 || image_data!==image[received]) $fatal(1,"input byte/order %0d",received);
            received=received+1;
        end
        if(real_valid) begin
            if(produced>=12288 || real_feature!==expected[produced]) $fatal(1,"output stream %0d",produced);
            produced=produced+1;
        end
        if(real_done && (!real_valid || produced!=12288)) $fatal(1,"last byte/done mismatch");
    end
    task automatic write_axi(input [15:0] address,input [31:0] data,input [3:0] strobe,
                             input integer order,input [1:0] expected_resp);
        reg [1:0] held;
        begin
            fork
                begin
                    if(order==2) repeat(3) @(negedge clk);
                    @(negedge clk);awaddr=address;awvalid=1;
                    do @(posedge clk); while(!awready);
                    @(negedge clk);awvalid=0;
                end
                begin
                    if(order==1) repeat(3) @(negedge clk);
                    @(negedge clk);wdata=data;wstrb=strobe;wvalid=1;
                    do @(posedge clk); while(!wready);
                    @(negedge clk);wvalid=0;
                end
            join
            while(!bvalid) @(negedge clk);
            held=bresp;
            repeat(3) begin @(negedge clk);if(!bvalid || bresp!==held) $fatal(1,"unstable B");end
            if(bresp!==expected_resp) $fatal(1,"BRESP addr=%h got=%h want=%h",address,bresp,expected_resp);
            bready=1;@(posedge clk);@(negedge clk);bready=0;
        end
    endtask
    task automatic read_axi(input [15:0] address,input [1:0] expected_resp,output [31:0] data);
        reg [31:0] held;
        reg [1:0] held_resp;
        begin
            @(negedge clk);araddr=address;arvalid=1;
            do @(posedge clk); while(!arready);
            @(negedge clk);arvalid=0;
            while(!rvalid) @(negedge clk);
            held=rdata;held_resp=rresp;
            repeat(2) begin
                @(negedge clk);
                if(!rvalid || rdata!==held || rresp!==held_resp) $fatal(1,"unstable R");
            end
            if(rresp!==expected_resp) $fatal(1,"RRESP addr=%h",address);
            data=rdata;rready=1;@(posedge clk);@(negedge clk);rready=0;
        end
    endtask
    task automatic expect_register(input [15:0] address,input [31:0] wanted);
        reg [31:0] got;
        begin read_axi(address,0,got);if(got!==wanted) $fatal(1,"reg=%h got=%h want=%h",address,got,wanted);end
    endtask
    task load_input;
        begin
            for(i=0;i<1024;i=i+1) begin
                word={image[i*4+3],image[i*4+2],image[i*4+1],image[i*4]};
                write_axi(16'h1000+i*4,word,15,i%3,0);
            end
            expect_register(16'h14,1024);
        end
    endtask
    task wait_idle;
        begin repeat(12) @(negedge clk);expect_register(8,1);expect_register(16'h14,0);end
    endtask
    initial begin
        found=$value$plusargs("DATA_DIR=%s",data_root);
        found=$value$plusargs("RESULT_FILE=%s",result_path);
        fd=$fopen(result_path,"w");if(!fd) $fatal(1,"result open failed");
        repeat(5) @(negedge clk);resetn=1;wait_idle();
        expect_register(0,32'h434e0100);
        if($test$plusargs("DIAG")) begin
            fake_mode=1;
            for(i=0;i<4096;i=i+1) image[i]=i%256;
            load_input();write_axi(4,1,15,0,0);
            repeat(17000) @(negedge clk);
            for(j=0;j<12288;j=j+1) begin
                fake_valid=1;fake_data=j%128;fake_done=(j==12287);
                @(negedge clk);
            end
            fake_valid=0;fake_done=0;
            repeat(5) @(negedge clk);expect_register(8,4);
            for(i=0;i<3072;i=i+1) begin
                read_axi(16'h4000+i*4,0,value);
                word=((i*4)%128)|(((i*4+1)%128)<<8)|(((i*4+2)%128)<<16)|(((i*4+3)%128)<<24);
                if(i<4) $display("DIAG read i=%0d bus=%h ram=%h addr=%h",i,value,dut.output_dout_b,dut.output_addr_b);
                if(value!==word) $fatal(1,"DIAG output %0d got=%h expected=%h",i,value,word);
            end
            $fdisplay(fd,"DIAG_PASS");$fclose(fd);$finish;
        end
        write_axi(4,1,15,1,2); // 未装图START。
        write_axi(16'h1000,32'hff807f00,1,2,2);
        expect_register(16'h14,0);
        write_axi(16'h1000,32'hff807f00,15,0,0);
        write_axi(16'h1000,32'h01020304,15,1,0);
        expect_register(16'h14,1);
        expect_register(16'h1000,32'h01020304);
        write_axi(16'h1001,0,15,2,2);
        write_axi(16'h2000,0,15,0,2);
        write_axi(16'h4000,0,15,0,2);
        read_axi(16'h4000,2,value);read_axi(16'h7000,2,value);
        write_axi(4,4,0,0,0);expect_register(16'h14,1);
        write_axi(4,4,15,1,0);wait_idle();
        // 模拟AXI复位打断已收到AW但尚未收到W，确认不遗留命令。
        @(negedge clk);awaddr=4;awvalid=1;
        do @(posedge clk);while(!awready);
        @(negedge clk);awvalid=0;resetn=0;
        repeat(3) @(negedge clk);resetn=1;wait_idle();
        $fdisplay(fd,"PASS AXI split/strobes/duplicates/bounds/reset");
        for(frame=0;frame<3;frame=frame+1) begin
            $sformat(path,"%0s/case%0d_input.mem",data_root,frame);$readmemh(path,image);
            $sformat(path,"%0s/case%0d_pool2.mem",data_root,frame);$readmemh(path,expected);
            load_input();
            for(i=0;i<1024;i=i+1) begin
                read_axi(16'h1000+i*4,0,value);
                if(value!=={image[i*4+3],image[i*4+2],image[i*4+1],image[i*4]}) $fatal(1,"RAM packing");
            end
            received=0;produced=0;checking=1;
            write_axi(4,1,15,frame%3,0);
            write_axi(16'h1000,0,15,0,2);write_axi(4,1,15,1,2);write_axi(4,2,15,2,2);
            read_axi(16'h4000,2,value);
            polls=0;value=2;
            while(value==2 && polls<200000) begin read_axi(8,0,value);polls=polls+1;end
            if(value!=4) $fatal(1,"frame failed state=%h error=%0d",value,dut.error_code);
            expect_register(16'h18,4096);expect_register(16'h1c,12288);expect_register(16'h10,frame+1);
            if(received!=4096 || produced!=12288) $fatal(1,"counts");
            checking=0;
            for(i=0;i<3072;i=i+1) begin
                read_axi(16'h4000+i*4,0,value);
                if(value!=={expected[i*4+3],expected[i*4+2],expected[i*4+1],expected[i*4]}) $fatal(1,"output RAM %0d got=%h expected=%h addr=%h",i,value,{expected[i*4+3],expected[i*4+2],expected[i*4+1],expected[i*4]},dut.output_addr_b);
            end
            // DONE期间非法启动/改写不会覆盖锁定结果。
            write_axi(4,1,15,0,2);write_axi(16'h1000,0,15,1,2);
            expect_register(16'h6ffc,{expected[12287],expected[12286],expected[12285],expected[12284]});
            $fdisplay(fd,"PASS REAL frame=%0d input=%0d output=%0d cycles=%0d",frame,received,produced,dut.cycles);
            $fflush(fd);
            write_axi(4,2,15,2,0);expect_register(8,1);expect_register(16'h14,0);
        end
        fake_mode=1;
        load_input();write_axi(4,1,15,0,0);
        @(negedge clk);fake_valid=1;fake_done=1;fake_data=127;
        @(negedge clk);fake_valid=0;fake_done=0;
        expect_register(8,8);expect_register(12,3);
        write_axi(4,2,15,0,0);wait_idle();
        load_input();write_axi(4,1,15,0,0);
        repeat(17000) @(negedge clk);
        fake_valid=1;
        repeat(12289) @(negedge clk);
        fake_valid=0;expect_register(8,8);expect_register(12,2);
        write_axi(4,4,15,0,0);wait_idle();
        load_input();write_axi(4,1,15,0,0);
        repeat(1000020) @(negedge clk);
        expect_register(8,8);expect_register(12,1);
        write_axi(4,4,15,0,0);wait_idle();
        load_input();write_axi(4,1,15,0,0);
        repeat(15) @(negedge clk);
        write_axi(4,4,15,0,0);wait_idle();
        $fdisplay(fd,"PASS injected early_done/overflow/watchdog/abort");
        // 恢复后再次运行真正的CNN，证明不是仅状态寄存器恢复。
        fake_mode=0;
        $sformat(path,"%0s/case0_input.mem",data_root);$readmemh(path,image);
        $sformat(path,"%0s/case0_pool2.mem",data_root);$readmemh(path,expected);
        load_input();received=0;produced=0;checking=1;
        read_axi(16'h10,0,seq);write_axi(4,1,15,0,0);
        value=2;polls=0;
        while(value==2 && polls<200000) begin read_axi(8,0,value);polls=polls+1;end
        if(value!=4 || received!=4096 || produced!=12288) $fatal(1,"real recovery");
        expect_register(16'h10,seq+1);
        expect_register(16'h6ffc,{expected[12287],expected[12286],expected[12285],expected[12284]});
        checking=0;
        $fdisplay(fd,"PASS REAL after_fault_recovery");
        $fdisplay(fd,"ALL_PASS AXI_REAL frames=3 recovery=1");$fclose(fd);
        $display("ALL_PASS AXI_REAL frames=3 recovery=1");$finish;
    end
    initial begin #59000000;$fatal(1,"global timeout");end
endmodule
