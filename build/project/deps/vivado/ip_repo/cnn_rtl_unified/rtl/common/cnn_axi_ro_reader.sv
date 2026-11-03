`timescale 1ns/1ps
// 单个未完成burst。取消/超时不撤销ARVALID，不复位计数；正确排空后才能quiescent。
// 外部resetn只能用于系统复位或已证明安全的本地复位，不能作为ABORT替代。
module cnn_axi_ro_reader (
    input wire clk, input wire resetn, input wire clear, input wire abort,
    input wire request_valid, output wire request_ready,
    input wire [31:0] request_address, input wire [15:0] request_bytes,
    input wire [15:0] request_capacity_bytes, input wire [31:0] stall_limit_cycles,
    output wire [63:0] data, output wire data_valid, input wire data_ready, output wire data_last,
    output wire busy, output wire quiescent, output wire ar_pending, output reg outstanding,
    output reg done, output reg error, output reg [3:0] error_code,
    output wire recovery_required, output reg protocol_poisoned,
    output reg [31:0] ar_count, output reg [31:0] r_count, output reg [31:0] last_araddr,
    output reg [3:0] last_r_meta, output reg [31:0] fault_flags,
    output reg [31:0] m_axi_araddr, output reg [7:0] m_axi_arlen,
    output wire m_axi_arid, output wire [2:0] m_axi_arsize, output wire [1:0] m_axi_arburst,
    output wire m_axi_arlock, output wire [3:0] m_axi_arcache,
    output wire [2:0] m_axi_arprot, output wire [3:0] m_axi_arqos,
    output reg m_axi_arvalid, input wire m_axi_arready,
    input wire m_axi_rid, input wire [63:0] m_axi_rdata, input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast, input wire m_axi_rvalid, output wire m_axi_rready
);
    localparam [3:0] ERR_AR_TIMEOUT=3, ERR_R_TIMEOUT=4, ERR_RRESP=5, ERR_RID=6, ERR_RLAST=7, ERR_REQUEST=11;
    reg active, cancelled, timed_out;
    reg [31:0] next_address, stall_count, latched_limit;
    reg [15:0] remaining_bytes;
    reg [4:0] burst_beats, received_beats;
    reg final_burst;
    reg [63:0] fifo_data [0:1];
    reg fifo_last [0:1];
    reg fifo_write_pointer, fifo_read_pointer;
    reg [1:0] fifo_count;
    wire [32:0] request_end={1'b0,request_address}+{17'd0,request_bytes};
    wire request_shape_ok=request_address!=0 && request_address[2:0]==0 &&
        request_bytes!=0 && request_bytes<=512 && request_bytes[2:0]==0 &&
        request_end<=33'h040000000 && stall_limit_cycles!=0;
    assign busy=active;
    assign ar_pending=m_axi_arvalid;
    assign quiescent=!active && !m_axi_arvalid && !outstanding && fifo_count==0 && !protocol_poisoned;
    assign recovery_required=protocol_poisoned || (timed_out && (m_axi_arvalid || outstanding));
    assign request_ready=quiescent && !error && !abort && (!request_shape_ok || request_capacity_bytes>=request_bytes);
    assign m_axi_arid=0; assign m_axi_arsize=3; assign m_axi_arburst=1;
    assign m_axi_arlock=0; assign m_axi_arcache=4'b0011; assign m_axi_arprot=0; assign m_axi_arqos=0;
    wire ar_handshake=m_axi_arvalid && m_axi_arready;
    wire r_handshake=m_axi_rvalid && m_axi_rready;
    wire timeout_now=(m_axi_arvalid||outstanding) && !ar_handshake && !r_handshake &&
        !cancelled && stall_count>=latched_limit-1'b1;
    // 超时仅在时钟沿注册为cancelled；不能让timeout_now组合反馈RREADY形成环。
    wire stopping=cancelled || abort || error || protocol_poisoned;
    assign data=fifo_data[fifo_read_pointer];
    assign data_last=fifo_last[fifo_read_pointer];
    assign data_valid=(fifo_count!=0) && !stopping;
    wire pop=data_valid && data_ready;
    assign m_axi_rready=outstanding ? (stopping || fifo_count<2 || pop) : !m_axi_arvalid;
    wire expected_last=received_beats==burst_beats-1'b1;
    wire response_bad=m_axi_rid!=0 || m_axi_rlast!=expected_last || m_axi_rresp!=0;
    wire push=r_handshake && outstanding && !stopping && !response_bad;
    wire [12:0] boundary_bytes=13'd4096-{1'b0,next_address[11:0]};
    wire [15:0] max_by_boundary=boundary_bytes<128 ? {3'd0,boundary_bytes} : 16'd128;
    wire [15:0] planned_bytes=remaining_bytes<max_by_boundary ? remaining_bytes : max_by_boundary;
    function [31:0] increment_sat(input [31:0] value);
        increment_sat=value==32'hffffffff ? value : value+1'b1;
    endfunction
    always @(posedge clk) begin
        if (!resetn) begin
            active<=0; cancelled<=0; timed_out<=0; next_address<=0; remaining_bytes<=0;
            burst_beats<=0; received_beats<=0; final_burst<=0; stall_count<=0; latched_limit<=1;
            fifo_count<=0; fifo_write_pointer<=0; fifo_read_pointer<=0;
            m_axi_araddr<=0; m_axi_arlen<=0; m_axi_arvalid<=0; outstanding<=0;
            done<=0; error<=0; error_code<=0; protocol_poisoned<=0;
            ar_count<=0;r_count<=0;last_araddr<=0;last_r_meta<=0;fault_flags<=0;
        end else begin
            done<=0;
            if (clear && quiescent) begin
                error<=0;error_code<=0;cancelled<=0;timed_out<=0;
                stall_count<=0;ar_count<=0;r_count<=0;last_araddr<=0;last_r_meta<=0;fault_flags<=0;
            end
            if (request_valid && request_ready) begin
                if (!request_shape_ok) begin error<=1;error_code<=ERR_REQUEST;end
                else begin
                    active<=1;cancelled<=0;timed_out<=0;next_address<=request_address;
                    remaining_bytes<=request_bytes;latched_limit<=stall_limit_cycles;stall_count<=0;
                end
            end
            // 整个逻辑块已在调用方预留；每个burst发出前还要求skid空，保证归属清晰。
            if (active && !stopping && !outstanding && !m_axi_arvalid && fifo_count==0 &&
                remaining_bytes!=0 && !m_axi_rvalid) begin
                m_axi_araddr<=next_address;
                m_axi_arlen<=(planned_bytes>>3)-1'b1;
                burst_beats<=planned_bytes>>3;
                final_burst<=planned_bytes==remaining_bytes;
                m_axi_arvalid<=1;
            end
            if (ar_handshake) begin
                m_axi_arvalid<=0;outstanding<=1;received_beats<=0;
                next_address<=next_address+{21'd0,m_axi_arlen,3'b000}+32'd8;
                remaining_bytes<=remaining_bytes-({5'd0,m_axi_arlen,3'b000}+16'd8);
                ar_count<=increment_sat(ar_count);last_araddr<=m_axi_araddr;
            end
            if (ar_handshake || r_handshake || !(m_axi_arvalid||outstanding)) stall_count<=0;
            else stall_count<=increment_sat(stall_count);
            if (abort && active) begin
                fault_flags[7]<=1;
                cancelled<=1;
                if (!error) begin error<=1;error_code<=1;end
            end
            if (timeout_now) begin
                if (m_axi_arvalid) fault_flags[0]<=1; else fault_flags[1]<=1;
                cancelled<=1;timed_out<=1;
                if (!error) begin error<=1;error_code<=m_axi_arvalid ? ERR_AR_TIMEOUT : ERR_R_TIMEOUT;end
            end
            if (r_handshake) begin
                last_r_meta<={m_axi_rid,m_axi_rlast,m_axi_rresp};
                r_count<=increment_sat(r_count);
                if (!outstanding) begin
                    fault_flags[4]<=1;
                    protocol_poisoned<=1;cancelled<=1;error<=1;
                    if (!error) error_code<=ERR_RLAST;
                end else begin
                    if (m_axi_rresp!=0) fault_flags[2]<=1;
                    if (m_axi_rid!=0) fault_flags[3]<=1;
                    if (m_axi_rlast!=expected_last) fault_flags[4]<=1;
                    if (received_beats!=31) received_beats<=received_beats+1'b1;
                    if (m_axi_rid!=0 || m_axi_rlast!=expected_last) begin
                        protocol_poisoned<=1;cancelled<=1;error<=1;
                        if (!error) error_code<=m_axi_rid!=0 ? ERR_RID : ERR_RLAST;
                    end else if (m_axi_rresp!=0) begin
                        cancelled<=1;error<=1;
                        if (!error) error_code<=ERR_RRESP;
                    end
                    if (expected_last && m_axi_rlast) outstanding<=0;
                end
            end
            // 取消/首错优先清除队列，不能被停止的消费者阻塞排空。
            if (stopping || (r_handshake && (!outstanding || response_bad))) begin
                fifo_count<=0;fifo_write_pointer<=0;fifo_read_pointer<=0;
            end else begin
                case ({push,pop})
                    2'b10:fifo_count<=fifo_count+1'b1;
                    2'b01:fifo_count<=fifo_count-1'b1;
                    default:begin end
                endcase
                if (push) begin
                    fifo_data[fifo_write_pointer]<=m_axi_rdata;
                    fifo_last[fifo_write_pointer]<=final_burst && expected_last;
                    fifo_write_pointer<=!fifo_write_pointer;
                end
                if (pop) fifo_read_pointer<=!fifo_read_pointer;
            end
            if (active && !m_axi_arvalid && !outstanding && fifo_count==0 &&
                (remaining_bytes==0 || cancelled || error)) begin
                active<=0;
                if (!error && !abort && !cancelled && !protocol_poisoned) done<=1;
            end
        end
    end
endmodule
