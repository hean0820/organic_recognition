`timescale 1ns / 1ps

// Preserve the original one-clock RGB/control alignment without a forced ROI.
// The camera's PS-rendered dashed guide remains camera-only; voice stays clean.
module hdmi_roi_overlay (
    input wire pclk,
    input wire reset,
    input wire [23:0] video_rgb_in,
    input wire video_de_in,
    input wire video_hsync_in,
    input wire video_vsync_in,
    output reg [23:0] video_rgb_out,
    output reg video_de_out,
    output reg video_hsync_out,
    output reg video_vsync_out
);
    always @(posedge pclk or posedge reset) begin
        if (reset) begin
            video_rgb_out <= 0;
            video_de_out <= 0;
            video_hsync_out <= 0;
            video_vsync_out <= 0;
        end else begin
            video_rgb_out <= video_rgb_in;
            video_de_out <= video_de_in;
            video_hsync_out <= video_hsync_in;
            video_vsync_out <= video_vsync_in;
        end
    end
endmodule
