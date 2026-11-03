// 16 kHz mono capture, 4096 PCM16 FIFO (256 ms), AXI4-Lite, PS GPIO.
// AXI address and data channels are accepted independently. One response outstanding.
module audio_axi #(
    parameter integer FIFO_BITS=12
)(
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *) input s_axi_aclk,
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *) input s_axi_aresetn,
    input [7:0] s_axi_awaddr,input [2:0] s_axi_awprot,input s_axi_awvalid,output s_axi_awready,
    input [31:0] s_axi_wdata,input [3:0] s_axi_wstrb,input s_axi_wvalid,output s_axi_wready,
    output [1:0] s_axi_bresp,output reg s_axi_bvalid,input s_axi_bready,
    input [7:0] s_axi_araddr,input [2:0] s_axi_arprot,input s_axi_arvalid,output s_axi_arready,
    output [31:0] s_axi_rdata,output [1:0] s_axi_rresp,output reg s_axi_rvalid,input s_axi_rready,
    input clock_locked,input aud_bclk,input aud_lrc,input aud_adcdat,
    output aud_dacdat,output aud_scl,inout aud_sda,input voice_key_n,output [1:0] voice_led
);
    localparam DEPTH=1<<FIFO_BITS;
    reg [31:0] control;reg [1:0] led;
    reg aw_pending,w_pending;reg [7:0] awaddr;reg [31:0] wdata;reg [3:0] wstrb;
    reg restart,flush;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_bresp=2'b00;assign s_axi_rresp=2'b00;
    assign s_axi_arready=!s_axi_rvalid;
    assign voice_led=led;
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            control<=32'h08;led<=0;aw_pending<=0;w_pending<=0;s_axi_bvalid<=0;
            awaddr<=0;wdata<=0;wstrb<=0;restart<=0;flush<=0;
        end else begin
            restart<=0;flush<=0;
            if(s_axi_awready && s_axi_awvalid) begin aw_pending<=1;awaddr<=s_axi_awaddr;end
            if(s_axi_wready && s_axi_wvalid) begin w_pending<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(aw_pending && w_pending && !s_axi_bvalid) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;
                if(awaddr==8'h04 && wstrb[0]) begin
                    control<={27'b0,wdata[4:3],1'b0,wdata[1:0]};
                    flush<=wdata[2] || (control[4:1]!={wdata[4:3],1'b0,wdata[1]});
                    restart<=control[4:1]!={wdata[4:3],1'b0,wdata[1]};
                end
                if(awaddr==8'h20 && wstrb[0]) led<=wdata[1:0];
            end
        end
    end
    wire cfg_ready,nack,fir_overrun,pcm_valid;wire signed [15:0] pcm;
    audio_pcm_core core(.clk(s_axi_aclk),.rst_n(s_axi_aresetn),.clock_locked(clock_locked),
        .restart(restart),.line_input(control[1]),.gain(control[4:3]),
        .aud_bclk(aud_bclk),.aud_lrc(aud_lrc),.aud_adcdat(aud_adcdat),
        .aud_dacdat(aud_dacdat),.aud_scl(aud_scl),.aud_sda(aud_sda),
        .cfg_ready(cfg_ready),.nack(nack),.fir_overrun(fir_overrun),.pcm_valid(pcm_valid),.pcm(pcm));
    (* ASYNC_REG="TRUE" *) reg [1:0] key_sync;
    always @(posedge s_axi_aclk)
        if(!s_axi_aresetn) key_sync<=3;else key_sync<={key_sync[0],voice_key_n};
    (* ram_style="block" *) reg [15:0] memory [0:DEPTH-1];
    reg [FIFO_BITS-1:0] wr_ptr,rd_ptr;
    reg [FIFO_BITS:0] count;
    reg [31:0] dropped,total;
    reg [15:0] memory_data;reg [31:0] register_data;reg read_pcm;
    wire read_accept=s_axi_arvalid && s_axi_arready;
    wire pop=read_accept && s_axi_araddr==8'h10 && count!=0 && !flush;
    wire push=pcm_valid && control[0] && (count<DEPTH || pop) && !flush;
    assign s_axi_rdata=read_pcm ? {{16{memory_data[15]}},memory_data}:register_data;
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            wr_ptr<=0;rd_ptr<=0;count<=0;dropped<=0;total<=0;
        end else if(flush) begin wr_ptr<=0;rd_ptr<=0;count<=0;dropped<=0;total<=0;end
        else begin
            if(push) wr_ptr<=wr_ptr+1'b1;
            if(pop) rd_ptr<=rd_ptr+1'b1;
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default: ;
            endcase
            if(pcm_valid && control[0]) begin
                total<=total+1'b1;
                if(!push) dropped<=dropped+1'b1;
            end
        end
    end
    always @(posedge s_axi_aclk) if(push) memory[wr_ptr]<=pcm;
    always @(posedge s_axi_aclk) if(pop) memory_data<=memory[rd_ptr];
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin s_axi_rvalid<=0;read_pcm<=0;register_data<=0;end
        else begin
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(read_accept) begin
                s_axi_rvalid<=1;read_pcm<=pop;
                case(s_axi_araddr)
                    8'h00:register_data<=32'h41554432;
                    8'h04:register_data<=control;
                    8'h08:register_data<={23'b0,key_sync[1],3'b0,dropped!=0,fir_overrun,nack,cfg_ready,clock_locked};
                    8'h0c:register_data<=count;
                    8'h10:register_data<=0;
                    8'h14:register_data<=dropped;
                    8'h18:register_data<=total;
                    8'h1c:register_data<=32'h00010000;
                    8'h20:register_data<={30'b0,led};
                    default:register_data<=0;
                endcase
            end
        end
    end
endmodule
