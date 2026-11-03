`timescale 1ns/1ps
// loader拥有cache写口；每次逻辑装载全成功且reader队列排空后才发布该区有效长度。
module cnn_model_loader (
    input wire clk, input wire resetn, input wire clear, input wire abort,
    input wire load_valid, output wire load_ready, input wire [31:0] load_address,
    input wire [15:0] load_bytes, input wire [9:0] load_destination,
    input wire [31:0] stall_limit_cycles,
    output reg busy, output reg loaded, output wire quiescent,
    output wire error, output wire [3:0] error_code, output wire recovery_required,
    output wire protocol_poisoned,
    output wire ar_pending, output wire outstanding,
    output wire [31:0] ar_count, output wire [31:0] r_count, output wire [31:0] last_araddr,
    output wire [3:0] last_r_meta, output wire [31:0] fault_flags,
    input wire read_enable, input wire [9:0] read_byte_address,
    output wire [7:0] read_data, output wire read_valid, output reg read_error,
    output reg [9:0] weight_valid_bytes, output reg [9:0] bias_valid_bytes,
    output wire [31:0] m_axi_araddr, output wire [7:0] m_axi_arlen,
    output wire m_axi_arid, output wire [2:0] m_axi_arsize, output wire [1:0] m_axi_arburst,
    output wire m_axi_arlock, output wire [3:0] m_axi_arcache,
    output wire [2:0] m_axi_arprot, output wire [3:0] m_axi_arqos,
    output wire m_axi_arvalid, input wire m_axi_arready,
    input wire m_axi_rid, input wire [63:0] m_axi_rdata, input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast, input wire m_axi_rvalid, output wire m_axi_rready
);
    wire reader_ready,reader_done,reader_busy,reader_quiet,reader_error;
    wire [3:0] reader_error_code;
    wire [63:0] stream_data;
    wire stream_valid,stream_last;
    reg local_error;
    reg [6:0] write_word;
    reg [15:0] pending_bytes;
    reg pending_bias;
    reg [1:0] read_pending;
    wire destination_ok=(load_destination==0 || load_destination==512) && load_bytes>0 && load_bytes<=512 && load_bytes[2:0]==0;
    assign error=local_error||reader_error;
    assign error_code=local_error ? 4'd11 : reader_error_code;
    assign load_ready=!busy && !error && !abort && read_pending==0 && (destination_ok ? reader_ready : 1'b1);
    assign quiescent=reader_quiet && !busy && read_pending==0;
    wire accept=load_valid && load_ready;
    wire stream_ready=busy && !abort && !error;
    wire cache_write=stream_valid && stream_ready;
    wire in_range=read_byte_address[9] ? ({1'b0,read_byte_address[8:0]}<bias_valid_bytes) :
                                                        ({1'b0,read_byte_address[8:0]}<weight_valid_bytes);
    wire cache_read=read_enable && !busy && !load_valid && !error && !abort && in_range;
    wire cache_read_valid;
    assign read_valid=cache_read_valid && !abort && !error;
    always @(posedge clk) begin
        if (!resetn) begin
            busy<=0;loaded<=0;local_error<=0;write_word<=0;pending_bytes<=0;pending_bias<=0;
            weight_valid_bytes<=0;bias_valid_bytes<=0;read_pending<=0;read_error<=0;
        end else begin
            loaded<=0;read_error<=read_enable && !cache_read;read_pending<={read_pending[0],cache_read};
            if (clear && quiescent) begin local_error<=0;weight_valid_bytes<=0;bias_valid_bytes<=0;end
            if (accept) begin
                if (!destination_ok) local_error<=1;
                else begin
                    busy<=1;write_word<=load_destination[9:3];pending_bytes<=load_bytes;
                    pending_bias<=load_destination[9];
                    if (load_destination[9]) bias_valid_bytes<=0; else weight_valid_bytes<=0;
                end
            end
            if (cache_write) write_word<=write_word+1'b1;
            if (reader_done && busy && !abort && !error) begin
                busy<=0;loaded<=1;
                if (pending_bias) bias_valid_bytes<=pending_bytes[9:0];else weight_valid_bytes<=pending_bytes[9:0];
            end
            if (abort || reader_error) begin
                weight_valid_bytes<=0;bias_valid_bytes<=0;
                if (reader_quiet) busy<=0;
            end
        end
    end
    cnn_model_cache cache (
        .clk(clk),.resetn(resetn),.write_enable(cache_write),.write_word_address(write_word),.write_data(stream_data),
        .read_enable(cache_read),.read_byte_address(read_byte_address),.read_data(read_data),.read_valid(cache_read_valid)
    );
    cnn_axi_ro_reader reader (
        .clk(clk),.resetn(resetn),.clear(clear),.abort(abort),
        .request_valid(load_valid && !busy && !local_error && !abort && read_pending==0 && destination_ok),
        .request_ready(reader_ready),.request_address(load_address),.request_bytes(load_bytes),
        .request_capacity_bytes(16'd512),.stall_limit_cycles(stall_limit_cycles),
        .data(stream_data),.data_valid(stream_valid),.data_ready(stream_ready),.data_last(stream_last),
        .busy(reader_busy),.quiescent(reader_quiet),.ar_pending(ar_pending),.outstanding(outstanding),
        .done(reader_done),.error(reader_error),.error_code(reader_error_code),.recovery_required(recovery_required),
        .protocol_poisoned(protocol_poisoned),.ar_count(ar_count),.r_count(r_count),.last_araddr(last_araddr),
        .last_r_meta(last_r_meta),.fault_flags(fault_flags),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arid(m_axi_arid),.m_axi_arsize(m_axi_arsize),
        .m_axi_arburst(m_axi_arburst),.m_axi_arlock(m_axi_arlock),.m_axi_arcache(m_axi_arcache),
        .m_axi_arprot(m_axi_arprot),.m_axi_arqos(m_axi_arqos),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rid(m_axi_rid),.m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),
        .m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready)
    );
endmodule
