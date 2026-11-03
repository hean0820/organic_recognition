module cnn_ps_if (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 s_axi_aclk CLK", X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input wire s_axi_aclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 s_axi_aresetn RST", X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *)
    input wire s_axi_aresetn,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWADDR", X_INTERFACE_PARAMETER="PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 16" *)
    input wire [15:0] s_axi_awaddr,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output wire s_axi_bvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [15:0] s_axi_araddr,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output wire [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output wire s_axi_rvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready
);
    wire [7:0] image_data, feature_data;
    wire image_valid, image_ready, feature_valid, frame_done, core_resetn;
    cnn_axi_buffer buffer (
        .clk(s_axi_aclk),.resetn(s_axi_aresetn),
        .awaddr(s_axi_awaddr),.awvalid(s_axi_awvalid),.awready(s_axi_awready),
        .wdata(s_axi_wdata),.wstrb(s_axi_wstrb),.wvalid(s_axi_wvalid),.wready(s_axi_wready),
        .bresp(s_axi_bresp),.bvalid(s_axi_bvalid),.bready(s_axi_bready),
        .araddr(s_axi_araddr),.arvalid(s_axi_arvalid),.arready(s_axi_arready),
        .rdata(s_axi_rdata),.rresp(s_axi_rresp),.rvalid(s_axi_rvalid),.rready(s_axi_rready),
        .image_data(image_data),.image_valid(image_valid),.image_ready(image_ready),
        .feature_data(feature_data),.feature_valid(feature_valid),.frame_done(frame_done),
        .core_resetn(core_resetn)
    );
    cnn_top #(.CONV2_LANES(2)) core (
        .sclk(s_axi_aclk),.s_rst_n(core_resetn),.image_data(image_data),
        .image_data_vld(image_valid),.image_data_ready(image_ready),
        .pool_data_out(feature_data),.pool_data_out_vld(feature_valid),.frame_done(frame_done)
    );
endmodule
