// Observation only. No monitor output drives the camera or video datapath.
// Clock the ILA from FCLK0, even when camera PCLK is absent.
module camera_signal_monitor(
    input wire clk, input wire cam_pclk, input wire cam_vsync, input wire cam_href,
    input wire locked, input wire video_resetn,
    input wire cmos_ce, input wire cmos_vsync, input wire cmos_active,
    input wire tvalid, input wire tready, input wire tuser, input wire tlast,
    input wire bridge_overflow, input wire bridge_underflow, input wire bridge_aresetn, input wire bridge_axis_enable,
    output wire [15:0] flags, output reg [31:0] heartbeat = 0,
    output reg [31:0] pclk_activity = 0,
    output wire [31:0] raw_events, output wire [31:0] cmos_events,
    output reg [31:0] axis_beats = 0, output wire [31:0] axis_events,
    output reg [31:0] axis_stalls = 0
);
    // Divide in the camera clock domain before observing activity in FCLK0.
    // One rising edge of bit 7 represents 256 camera cycles. This is an
    // activity indication, not a calibrated frequency measurement.
    reg [7:0] pclk_div = 0;
    always @(posedge cam_pclk) pclk_div <= pclk_div + 1'b1;
    (* ASYNC_REG = "TRUE" *) reg [6:0] sync1 = 0, sync2 = 0;
    reg [6:0] previous = 0;
    (* ASYNC_REG = "TRUE" *) reg [2:0] error_sync1 = 0, error_sync2 = 0;
    reg overflow_seen = 0, underflow_seen = 0;
    reg [15:0] raw_frames = 0, raw_lines = 0, cmos_frames = 0, cmos_lines = 0;
    reg [15:0] axis_frames = 0, axis_lines = 0;
    wire [6:0] asynchronous = {locked, cmos_active, cmos_vsync, cmos_ce,
                               cam_href, cam_vsync, pclk_div[7]};
    always @(posedge clk) begin
        error_sync1 <= {bridge_axis_enable, bridge_underflow, bridge_overflow};
        error_sync2 <= error_sync1;
        overflow_seen <= overflow_seen | error_sync2[0];
        underflow_seen <= underflow_seen | error_sync2[1];
        sync1 <= asynchronous;
        sync2 <= sync1;
        previous <= sync2;
        heartbeat <= heartbeat + 1'b1;
        if (sync2[0] && !previous[0]) pclk_activity <= pclk_activity + 1'b1;
        if (sync2[1] && !previous[1]) raw_frames <= raw_frames + 1'b1;
        if (sync2[2] && !previous[2]) raw_lines <= raw_lines + 1'b1;
        if (sync2[4] && !previous[4]) cmos_frames <= cmos_frames + 1'b1;
        if (sync2[5] && !previous[5]) cmos_lines <= cmos_lines + 1'b1;
        if (video_resetn && tvalid && tready) begin
            axis_beats <= axis_beats + 1'b1;
            if (tuser) axis_frames <= axis_frames + 1'b1;
            if (tlast) axis_lines <= axis_lines + 1'b1;
        end
        if (video_resetn && tvalid && !tready) axis_stalls <= axis_stalls + 1'b1;
    end
    assign flags = {error_sync2[2], bridge_aresetn, underflow_seen, overflow_seen, tlast, tuser, tready, tvalid, sync2[5], sync2[4], sync2[3],
                     sync2[2], sync2[1], sync2[0], video_resetn, sync2[6]};
    assign raw_events = {raw_frames, raw_lines};
    assign cmos_events = {cmos_frames, cmos_lines};
    assign axis_events = {axis_frames, axis_lines};
endmodule

