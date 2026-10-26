`timescale 1ns/1ps
// One autonomous network transaction, no PS feature transfer. Frontend compute
// body is the proven two-lane implementation; only local frontend reset on fault.
module cnn_unified_core #(
    parameter integer CONV3_LANES = 4
) (
    input wire clk,resetn,start,clear,abort,
    input wire [31:0] weight_base,bias_base,ddr_stall_limit_cycles,
    output wire quiescent,output reg done,error,output reg [3:0] error_code,
    output wire recovery_required,protocol_poisoned,ar_pending,outstanding,
    output wire [7:0] stage,output reg [31:0] pool2_bytes,pool3_bytes,
    output wire [31:0] ar_count,r_count,last_araddr,fault_flags,output wire [3:0] last_r_meta,
    output wire logit_valid,output wire [4:0] logit_index,output wire signed [31:0] logit,
    output wire input_read,output wire [11:0] input_address,input wire [7:0] input_data,input wire input_valid,
    input wire debug_request,input wire [1:0] debug_select,input wire [13:0] debug_index,
    output wire debug_valid,output wire [7:0] debug_data,
    output wire [31:0] m_axi_araddr,output wire [7:0] m_axi_arlen,output wire m_axi_arid,
    output wire [2:0] m_axi_arsize,output wire [1:0] m_axi_arburst,output wire m_axi_arlock,
    output wire [3:0] m_axi_arcache,output wire [2:0] m_axi_arprot,output wire [3:0] m_axi_arqos,
    output wire m_axi_arvalid,input wire m_axi_arready,input wire m_axi_rid,input wire [63:0] m_axi_rdata,
    input wire [1:0] m_axi_rresp,input wire m_axi_rlast,m_axi_rvalid,output wire m_axi_rready
);
    localparam IDLE=0,BIAS_LOAD=1,FRONTEND=2,C3_RUN=3,FC_RUN=4,COMMIT=6,COMPLETE=7,DRAIN=8,FAULT=9,
               BIAS_WAIT=12,FRONT_DRAIN=13,C3_START=14,FC_START=15;
    reg [3:0] phase;reg [7:0] fault_stage;
    reg [31:0] weights_latched,bias_latched;reg [4:0] drain;
    reg [1:0] feed_state;reg [11:0] feed_address;reg [7:0] feed_data;
    reg [12:0] feed_count;reg [1:0] input_pending;
    reg [4:0] frontend_activity;
    reg [31:0] local_flags;
    wire loader_quiet,loader_error,loader_loaded,load_ready,read_error;
    wire [3:0] loader_code,c3_code,fc_code;
    wire c3_busy,c3_done,c3_error,fc_busy,fc_done,fc_error,fc_result;
    wire c3_load,fc_load,c3_cache_read,fc_cache_read,cache_valid;
    wire [31:0] c3_load_address,fc_load_address;wire[15:0]c3_load_bytes,fc_load_bytes;
    wire [9:0] c3_cache_address,fc_cache_address;wire[7:0]cache_data;
    wire c3_quant,fc_quant,quant_result_valid;wire signed[31:0] c3_quant_acc,fc_quant_acc;wire[7:0]quant_result;
    wire c3_p2_read,fc_p3_read,p2_valid,p3_valid,p3_write;
    wire [13:0] c3_p2_address;wire [11:0] fc_p3_address,p3_write_address;wire[7:0]p2_data,p3_data,p3_write_data;
    wire [31:0] c3_count;wire [5:0] hidden_count,logit_count;
    // Count-to-address permutation for grouped output-channel commits.
    // Preserve strict one-write-per-position checking; memory remains CHW for FC/debug.
    wire [11:0] expected_pool3_address = CONV3_LANES==4 ?
        {pool3_bytes[11:8],pool3_bytes[1:0],pool3_bytes[7:2]} :
        {pool3_bytes[11:7],pool3_bytes[0],pool3_bytes[6:1]};
    wire fc_logit_valid;wire[4:0]fc_logit_index;wire signed[31:0]fc_logit;
    wire [7:0] hidden_debug;wire hidden_debug_valid;
    wire [31:0] reader_flags;
    wire front_ready,front_done,front_valid;wire[7:0]front_data;
    wire active=phase!=IDLE && phase!=COMPLETE && phase!=FAULT;
    wire halt=abort || error || loader_error || c3_error || fc_error || phase==DRAIN;
    wire front_resetn=resetn && phase!=DRAIN && phase!=FAULT;
    wire front_image_valid=phase==FRONTEND && feed_state==2 && !halt;
    wire front_write=phase==FRONTEND && front_valid && !halt && pool2_bytes<12288;
    // FC2 selection is exposed by the engine's diagnostic phase output.
    wire fc_phase2;
    assign stage=error?fault_stage:((phase==FC_RUN && fc_phase2)?8'd5:
        phase==BIAS_WAIT?8'd1:phase==FRONT_DRAIN?8'd2:phase==C3_START?8'd3:phase==FC_START?8'd4:{4'd0,phase});
    wire [7:0] stage_before_error=(phase==FC_RUN && fc_phase2)?8'd5:
        phase==BIAS_WAIT?8'd1:phase==FRONT_DRAIN?8'd2:phase==C3_START?8'd3:phase==FC_START?8'd4:{4'd0,phase};
    assign input_read=phase==FRONTEND && feed_state==0 && !halt;
    assign input_address=feed_address;
    cnn_top #(.CONV2_LANES(2)) frontend(.sclk(clk),.s_rst_n(front_resetn),.image_data_vld(front_image_valid),.image_data(feed_data),
        .pool_data_out(front_data),.pool_data_out_vld(front_valid),.image_data_ready(front_ready),.frame_done(front_done));
    wire use_c3=phase==C3_RUN;wire use_fc=phase==FC_RUN;
    wire model_load=(phase==BIAS_LOAD || (use_c3&&c3_load) || (use_fc&&fc_load)) && !halt;
    wire [31:0] model_address=phase==BIAS_LOAD?bias_latched:use_c3?c3_load_address:fc_load_address;
    wire [15:0] model_bytes=phase==BIAS_LOAD?16'd472:use_c3?c3_load_bytes:fc_load_bytes;
    wire cache_read=(use_c3&&c3_cache_read)||(use_fc&&fc_cache_read);
    wire [9:0] cache_address=use_c3?c3_cache_address:fc_cache_address;
    wire quant_valid=(use_c3&&c3_quant)||(use_fc&&fc_quant);
    reg [1:0] weight_read_pipe;
    wire invalid_weight=weight_read_pipe[1] && cache_valid && cache_data==8'h80;
    wire bad_front=(front_valid && phase!=FRONTEND && phase!=DRAIN && phase!=FAULT) ||
        (phase==FRONTEND && ((front_valid && pool2_bytes>=12288) || (front_done && (!front_valid || pool2_bytes!=12287))));
    wire bad_activation=front_write && front_data>127;
    reg [1:0] debug_pipe;reg[1:0]debug_sel0,debug_sel1;reg[7:0]hidden0,hidden1;
    wire dbg=debug_request && phase==COMPLETE && !halt && !clear;
    wire debug_p2=dbg&&debug_select==1;wire debug_p3=dbg&&debug_select==2;
    wire [13:0] p2_address=use_c3?c3_p2_address:debug_index;
    wire [11:0] p3_address=use_fc?fc_p3_address:debug_index[11:0];
    assign debug_valid=debug_pipe[1] && phase==COMPLETE && !halt && !clear &&
        ((debug_sel1==1&&p2_valid)||(debug_sel1==2&&p3_valid)||(debug_sel1==3));
    assign debug_data=debug_sel1==1?p2_data:debug_sel1==2?p3_data:hidden1;
    assign quiescent=(phase==IDLE||phase==COMPLETE||phase==FAULT) && loader_quiet && !c3_busy && !fc_busy &&
        input_pending==0 && frontend_activity==0 && debug_pipe==0 && !debug_request;
    assign logit_valid=use_fc && fc_logit_valid && !halt;
    assign logit_index=fc_logit_index;assign logit=fc_logit;
    assign fault_flags=reader_flags|local_flags;
    cnn_pool2_store pool2(.clk(clk),.resetn(resetn),.owner_conv3(use_c3||debug_p2),.write_enable(front_write),
        .write_address(pool2_bytes[13:0]),.write_data(front_data),.read_enable((use_c3&&c3_p2_read)||debug_p2),
        .read_address(p2_address),.read_data(p2_data),.read_valid(p2_valid),.rejected_write());
    cnn_pool3_store pool3(.clk(clk),.resetn(resetn),.write_enable(use_c3&&p3_write&&!halt),.write_address(p3_write_address),
        .write_data(p3_write_data),.read_enable((use_fc&&fc_p3_read)||debug_p3),.read_address(p3_address),.read_data(p3_data),.read_valid(p3_valid));
    cnn_quantize quant(.clk(clk),.resetn(resetn),.in_valid(quant_valid&&!halt),.acc_s32(use_c3?c3_quant_acc:fc_quant_acc),
        .multiplier_q30(use_c3?32'd6503432:32'd3488065),.out_valid(quant_result_valid),.activation_u8(quant_result));
    cnn_conv3_pool3 #(.LANES(CONV3_LANES)) c3(.clk(clk),.resetn(resetn),.start(phase==C3_START&&!halt),.clear(clear),.abort(halt),.weight_base(weights_latched),
        .busy(c3_busy),.done(c3_done),.error(c3_error),.error_code(c3_code),.pool2_read_enable(c3_p2_read),.pool2_byte_address(c3_p2_address),.pool2_data(p2_data),.pool2_valid(p2_valid),
        .cache_load_valid(c3_load),.cache_load_ready(load_ready&&use_c3),.cache_load_address(c3_load_address),.cache_load_bytes(c3_load_bytes),
        .cache_loaded(loader_loaded),.cache_error(loader_error||read_error),.cache_quiescent(loader_quiet),
        .cache_read_enable(c3_cache_read),.cache_read_address(c3_cache_address),.cache_data(cache_data),.cache_valid(cache_valid),
        .quant_valid(c3_quant),.quant_acc_s32(c3_quant_acc),.quant_result_valid(quant_result_valid&&use_c3),.quant_result(quant_result),
        .pool3_write_enable(p3_write),.pool3_byte_address(p3_write_address),.pool3_data(p3_write_data),.pool3_count(c3_count),
        .diagnostic_acc_valid(),.diagnostic_address(),.diagnostic_acc(),.diagnostic_activation_valid(),.diagnostic_activation());
    cnn_fc fc(.clk(clk),.resetn(resetn),.start(phase==FC_START&&!halt),.clear(clear),.abort(halt),.weight_base(weights_latched),
        .busy(fc_busy),.done(fc_done),.error(fc_error),.error_code(fc_code),.pool3_read_enable(fc_p3_read),.pool3_byte_address(fc_p3_address),.pool3_data(p3_data),.pool3_valid(p3_valid),
        .cache_load_valid(fc_load),.cache_load_ready(load_ready&&use_fc),.cache_load_address(fc_load_address),.cache_load_bytes(fc_load_bytes),
        .cache_loaded(loader_loaded),.cache_error(loader_error||read_error),.cache_quiescent(loader_quiet),.cache_read_enable(fc_cache_read),
        .cache_read_address(fc_cache_address),.cache_data(cache_data),.cache_valid(cache_valid),.quant_valid(fc_quant),.quant_acc_s32(fc_quant_acc),
        .quant_result_valid(quant_result_valid&&use_fc),.quant_result(quant_result),.logit_valid(fc_logit_valid),.logit_index(fc_logit_index),.logit_s32(fc_logit),
        .hidden_count(hidden_count),.logit_count(logit_count),.argmax_index(),.argmax_score(),.result_valid(fc_result),
        .hidden_debug_index(debug_index[5:0]),.hidden_debug_data(hidden_debug),.hidden_debug_valid(hidden_debug_valid),
        .diagnostic_partial_valid(),.diagnostic_fc2(fc_phase2),.diagnostic_output_index(),.diagnostic_chunk(),.diagnostic_acc(),.diagnostic_hidden_valid(),.diagnostic_hidden());
    cnn_model_loader loader(.clk(clk),.resetn(resetn),.clear(clear),.abort(halt),.load_valid(model_load),.load_ready(load_ready),
        .load_address(model_address),.load_bytes(model_bytes),.load_destination(phase==BIAS_LOAD?10'd512:10'd0),.stall_limit_cycles(ddr_stall_limit_cycles),
        .busy(),.loaded(loader_loaded),.quiescent(loader_quiet),.error(loader_error),.error_code(loader_code),.recovery_required(recovery_required),.protocol_poisoned(protocol_poisoned),
        .ar_pending(ar_pending),.outstanding(outstanding),.ar_count(ar_count),.r_count(r_count),.last_araddr(last_araddr),.last_r_meta(last_r_meta),.fault_flags(reader_flags),
        .read_enable(cache_read),.read_byte_address(cache_address),.read_data(cache_data),.read_valid(cache_valid),.read_error(read_error),.weight_valid_bytes(),.bias_valid_bytes(),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arid(m_axi_arid),.m_axi_arsize(m_axi_arsize),.m_axi_arburst(m_axi_arburst),
        .m_axi_arlock(m_axi_arlock),.m_axi_arcache(m_axi_arcache),.m_axi_arprot(m_axi_arprot),.m_axi_arqos(m_axi_arqos),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rid(m_axi_rid),.m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready));
    wire engine_fault=(c3_error||fc_error);
    wire [3:0] engine_code=c3_error?c3_code:fc_code;
    wire [3:0] mapped_error=abort?4'd1:loader_error?loader_code:invalid_weight?4'd13:bad_activation?4'd12:
        bad_front?4'd8:engine_fault?(engine_code==4?4'd12:4'd11):4'd11;
    always @(posedge clk) begin
        if(!resetn)begin
            phase<=IDLE;fault_stage<=0;weights_latched<=0;bias_latched<=0;drain<=0;done<=0;error<=0;error_code<=0;
            pool2_bytes<=0;pool3_bytes<=0;feed_state<=3;feed_address<=0;feed_data<=0;feed_count<=0;input_pending<=0;
            frontend_activity<=0;local_flags<=0;weight_read_pipe<=0;debug_pipe<=0;debug_sel0<=0;debug_sel1<=0;hidden0<=0;hidden1<=0;
        end else begin
            done<=0;input_pending<={input_pending[0],input_read};
            frontend_activity<={frontend_activity[3:0],(!front_ready||front_valid||front_image_valid)};
            weight_read_pipe<={weight_read_pipe[0],cache_read&&!cache_address[9]};
            debug_pipe<={debug_pipe[0],dbg};debug_sel0<=debug_select;debug_sel1<=debug_sel0;hidden0<=hidden_debug;hidden1<=hidden0;
            if(clear && (phase==IDLE||phase==COMPLETE||phase==FAULT) && quiescent) begin
                phase<=IDLE;error<=0;error_code<=0;local_flags<=0;pool2_bytes<=0;pool3_bytes<=0;feed_state<=3;
            end
            if(active && phase!=DRAIN && (abort||loader_error||engine_fault||read_error||bad_front||bad_activation||invalid_weight))begin
                phase<=DRAIN;drain<=0;error<=1;error_code<=mapped_error;fault_stage<=stage_before_error;feed_state<=3;
                local_flags[8]<=bad_front;local_flags[9]<=engine_fault;local_flags[10]<=read_error;local_flags[11]<=invalid_weight||bad_activation;
            end else case(phase)
                IDLE:if(start&&!abort&&!error)begin
                    weights_latched<=weight_base;bias_latched<=bias_base;phase<=BIAS_LOAD;pool2_bytes<=0;pool3_bytes<=0;feed_count<=0;feed_address<=0;feed_state<=3;local_flags<=0;
                end
                BIAS_LOAD:if(load_ready)phase<=BIAS_WAIT;
                BIAS_WAIT:if(loader_loaded)begin phase<=FRONTEND;feed_state<=0;end
                FRONTEND:begin
                    case(feed_state)
                        0:feed_state<=1;
                        1:if(input_valid)begin feed_data<=input_data;feed_state<=2;end
                        2:if(front_ready)begin
                            feed_count<=feed_count+1'b1;
                            if(feed_address==4095)feed_state<=3;else begin feed_address<=feed_address+1'b1;feed_state<=0;end
                        end
                        default:;
                    endcase
                    if(front_write)pool2_bytes<=pool2_bytes+1'b1;
                    if(front_done)begin
                        if(feed_count!=4096)begin phase<=DRAIN;drain<=0;error<=1;error_code<=8;fault_stage<=2;end
                        else begin phase<=FRONT_DRAIN;drain<=0;end
                    end
                end
                FRONT_DRAIN:if(drain!=16)drain<=drain+1'b1;else phase<=C3_START;
                C3_START:phase<=C3_RUN;
                C3_RUN:begin
                    if(p3_write&&!halt)begin
                        if(p3_write_address!=expected_pool3_address || pool3_bytes>=3072 || p3_write_data>127)begin phase<=DRAIN;drain<=0;error<=1;error_code<=9;fault_stage<=3;end
                        else pool3_bytes<=pool3_bytes+1'b1;
                    end
                    if(c3_done)begin
                        if(pool3_bytes!=3072||c3_count!=3072)begin phase<=DRAIN;drain<=0;error<=1;error_code<=9;fault_stage<=3;end
                        else phase<=FC_START;
                    end
                end
                FC_START:phase<=FC_RUN;
                FC_RUN:if(fc_done)begin phase<=COMMIT;drain<=0;end
                COMMIT:begin
                    if(drain!=16)drain<=drain+1'b1;
                    else if(loader_quiet&&!c3_busy&&!fc_busy&&input_pending==0&&frontend_activity==0)begin
                        if(pool2_bytes!=12288||pool3_bytes!=3072||hidden_count!=48||logit_count!=22||!fc_result)begin error<=1;error_code<=10;fault_stage<=6;phase<=DRAIN;drain<=0;end
                        else begin phase<=COMPLETE;done<=1;end
                    end
                end
                DRAIN:begin
                    feed_state<=3;
                    if(abort&&!error)begin error<=1;error_code<=1;fault_stage<=8;end
                    if(drain!=16)drain<=drain+1'b1;
                    else if(loader_quiet&&!c3_busy&&!fc_busy&&input_pending==0&&frontend_activity==0)phase<=FAULT;
                end
                default:;
            endcase
        end
    end
endmodule
