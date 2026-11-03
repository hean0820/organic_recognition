// Independent reset release in each clock domain. GPIO ctrl[0] releases reset;
// ctrl[1] enables AXIS. Power-on GPIO=0 holds the bridge in reset during SCCB.
module camera_bridge_reset_gate(
    input wire clk, input wire cam_pclk, input wire ps_resetn, input wire locked,
    input wire [1:0] ctrl, input wire overflow, input wire underflow,
    output wire bridge_aresetn,
    output wire native_hold, // Active high: drives vid_io_in_reset.
    output wire bridge_axis_enable, output wire [5:0] status
);
    wire release_request = ctrl[0] && ps_resetn && locked;
    reg [2:0] axi_release = 0;
    reg [2:0] vid_release = 0;
    (* ASYNC_REG = "TRUE" *) reg vid_request_sync1 = 0, vid_request_sync2 = 0;
    (* ASYNC_REG = "TRUE" *) reg vid_enable_sync1 = 0, vid_enable_sync2 = 0;
    always @(posedge clk) begin
        if (!release_request) axi_release <= 0;
        else axi_release <= {axi_release[1:0], 1'b1};
    end
    always @(posedge cam_pclk) begin
        vid_request_sync1 <= release_request;
        vid_request_sync2 <= vid_request_sync1;
        vid_enable_sync1 <= ctrl[1];
        vid_enable_sync2 <= vid_enable_sync1;
        if (!vid_request_sync2) vid_release <= 0;
        else vid_release <= {vid_release[1:0], 1'b1};
    end
    assign bridge_aresetn = axi_release[2];
    assign native_hold = !vid_release[2];
    // PG043: axis_enable is synchronous to vid_io_in_clk, not ACLK.
    assign bridge_axis_enable = vid_release[2] && vid_enable_sync2;
    // Status returns to the FCLK domain before PS reads GPIO channel 2.
    (* ASYNC_REG = "TRUE" *) reg [3:0] status_sync1 = 0, status_sync2 = 0;
    always @(posedge clk) begin
        status_sync1 <= {overflow, bridge_axis_enable, vid_release[2], locked};
        status_sync2 <= status_sync1;
    end
    assign status = {underflow, status_sync2[3], status_sync2[2],
                     status_sync2[1], bridge_aresetn, status_sync2[0]};
endmodule
