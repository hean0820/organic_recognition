// AXI控制与缓冲所有权；算法通过逐字节端口接入，便于单独注入协议故障。
module cnn_axi_buffer #(
    parameter integer WATCHDOG_CYCLES = 10000000
) (
    input wire clk, input wire resetn,
    input wire [15:0] awaddr, input wire awvalid, output wire awready,
    input wire [31:0] wdata, input wire [3:0] wstrb, input wire wvalid, output wire wready,
    output reg [1:0] bresp, output reg bvalid, input wire bready,
    input wire [15:0] araddr, input wire arvalid, output wire arready,
    output reg [31:0] rdata, output reg [1:0] rresp, output reg rvalid, input wire rready,
    output reg [7:0] image_data, output reg image_valid, input wire image_ready,
    input wire [7:0] feature_data, input wire feature_valid, input wire frame_done,
    output wire core_resetn
);
    localparam [2:0] IDLE=0, RUN=1, COMMIT=2, DONE=3, ERROR=4, RESETTING=5;
    localparam [31:0] PROTOCOL_ID=32'h434e0301;
    localparam [31:0] ERR_TIMEOUT=1, ERR_COUNT=2, ERR_DONE=3;
    reg [2:0] state;
    reg [31:0] error_code, sequence, cycles;
    reg [10:0] valid_words;
    reg [1023:0] input_valid_map;
    reg [12:0] input_count;
    reg [13:0] output_count;
    reg [3:0] reset_count;
    reg aw_pending, w_pending;
    reg [15:0] saved_awaddr;
    reg [31:0] saved_wdata;
    reg [3:0] saved_wstrb;
    reg [1:0] feed_phase;
    reg input_we;
    reg [9:0] input_addr_a;
    reg [31:0] input_din_a;
    reg input_en_b;
    reg [11:0] input_addr_b;
    wire [31:0] input_dout_a;
    wire [7:0] input_dout_b;
    reg output_en_b;
    reg [11:0] output_addr_b;
    wire [31:0] output_dout_b;
    reg [1:0] read_delay;
    reg read_output;
    wire write_execute = aw_pending && w_pending && !bvalid;
    wire output_we = state==RUN && feature_valid && output_count<14'd12288;
    wire [31:0] command_mask = saved_wdata & {{8{saved_wstrb[3]}},{8{saved_wstrb[2]}},
                                                              {8{saved_wstrb[1]}},{8{saved_wstrb[0]}}};
    assign awready = resetn && !aw_pending && !bvalid && read_delay==0;
    assign wready = resetn && !w_pending && !bvalid && read_delay==0;
    // 输入RAM A口读写串行，防止碰撞时读到厂商模型未定义的数据。
    assign arready = resetn && !rvalid && read_delay==0 && !aw_pending && !w_pending
                    && !awvalid && !wvalid && !input_we;
    assign core_resetn = resetn && state!=RESETTING && state!=ERROR;

    cnn_input_bram input_ram (
        .clka(clk), .wea(input_we), .addra(input_addr_a),
        .dina(input_din_a), .douta(input_dout_a),
        .clkb(clk), .enb(input_en_b), .web(1'b0), .addrb(input_addr_b),
        .dinb(8'd0), .doutb(input_dout_b)
    );
    cnn_output_bram output_ram (
        .clka(clk), .ena(output_we), .wea(output_we), .addra(output_count), .dina(feature_data),
        .clkb(clk), .enb(output_en_b), .addrb(output_addr_b), .doutb(output_dout_b)
    );

    always @(posedge clk) begin
        if (!resetn) begin
            state<=RESETTING; reset_count<=0;
            error_code<=0; sequence<=0; cycles<=0;
            valid_words<=0; input_valid_map<=0; input_count<=0; output_count<=0;
            aw_pending<=0; w_pending<=0; saved_awaddr<=0; saved_wdata<=0; saved_wstrb<=0;
            bvalid<=0; bresp<=0; rvalid<=0; rresp<=0; rdata<=0;
            input_we<=0; input_addr_a<=0; input_din_a<=0;
            input_en_b<=0; input_addr_b<=0; output_en_b<=0; output_addr_b<=0;
            read_delay<=0; read_output<=0; image_valid<=0; image_data<=0; feed_phase<=0;
        end else begin
            input_we<=0; input_en_b<=0; output_en_b<=0;
            if (bvalid && bready) bvalid<=0;
            if (rvalid && rready) rvalid<=0;
            if (awvalid && awready) begin saved_awaddr<=awaddr; aw_pending<=1; end
            if (wvalid && wready) begin saved_wdata<=wdata; saved_wstrb<=wstrb; w_pending<=1; end

            if (read_delay!=0) begin
                if(read_output && read_delay>1) output_en_b<=1;
                read_delay<=read_delay-1'b1;
                if (read_delay==1) begin
                    rdata<=read_output ? output_dout_b : input_dout_a;
                    rresp<=0; rvalid<=1;
                end
            end
            if (arvalid && arready) begin
                rresp<=0; rdata<=0;
                if (araddr[1:0]!=0) begin rresp<=2; rvalid<=1; end
                else if (araddr>=16'h1000 && araddr<16'h2000 && state==IDLE) begin
                    input_addr_a<=araddr[11:2]; read_delay<=2; read_output<=0;
                end else if (araddr>=16'h4000 && araddr<16'h7000 && state==DONE) begin
                    output_addr_b<=(araddr-16'h4000)>>2;
                    output_en_b<=1; read_delay<=3; read_output<=1;
                end else begin
                    rvalid<=1;
                    case (araddr)
                        16'h0000: rdata<=PROTOCOL_ID;
                        16'h0008: case(state)
                            IDLE:rdata<=1; RUN,COMMIT:rdata<=2; DONE:rdata<=4;
                            ERROR:rdata<=8; default:rdata<=16;
                        endcase
                        16'h000c:rdata<=error_code;
                        16'h0010:rdata<=sequence;
                        16'h0014:rdata<={21'd0,valid_words};
                        16'h0018:rdata<={19'd0,input_count};
                        16'h001c:rdata<={18'd0,output_count};
                        16'h0020:rdata<=cycles;
                        default:rresp<=2;
                    endcase
                end
            end

            if (state==RESETTING) begin
                image_valid<=0; feed_phase<=0;
                if (reset_count==7) begin
                    state<=IDLE; reset_count<=0; error_code<=0;
                    valid_words<=0; input_valid_map<=0; input_count<=0; output_count<=0; cycles<=0;
                end else reset_count<=reset_count+1'b1;
            end
            if (state==COMMIT) state<=DONE;
            if (state==RUN) begin
                cycles<=cycles+1'b1;
                if (input_count<13'd4096) begin
                    case(feed_phase)
                        0:begin input_addr_b<=input_count[11:0];input_en_b<=1;feed_phase<=1;end
                        1:feed_phase<=2;
                        2:begin image_data<=input_dout_b;image_valid<=1;feed_phase<=3;end
                        3:if(image_valid && image_ready) begin
                            input_count<=input_count+1'b1;image_valid<=0;feed_phase<=0;
                        end
                    endcase
                end
                if (feature_valid) begin
                    if (output_count<14'd12288) output_count<=output_count+1'b1;
                    else begin state<=ERROR;error_code<=ERR_COUNT;image_valid<=0;end
                end
                if (frame_done) begin
                    image_valid<=0;
                    if (!feature_valid || output_count!=14'd12287 || input_count!=13'd4096) begin
                        state<=ERROR;error_code<=ERR_DONE;
                    end else state<=COMMIT;
                end else if (cycles>=WATCHDOG_CYCLES-1) begin
                    state<=ERROR;error_code<=ERR_TIMEOUT;image_valid<=0;
                end
            end

            if (write_execute) begin
                aw_pending<=0;w_pending<=0;bvalid<=1;bresp<=0;
                if (saved_awaddr[1:0]!=0) bresp<=2;
                else if (saved_awaddr>=16'h1000 && saved_awaddr<16'h2000 && state==IDLE) begin
                    if (saved_wstrb!=4'hf) bresp<=2;
                    else begin
                        input_we<=1;input_addr_a<=saved_awaddr[11:2];input_din_a<=saved_wdata;
                        if (!input_valid_map[saved_awaddr[11:2]]) begin
                            input_valid_map[saved_awaddr[11:2]]<=1;valid_words<=valid_words+1'b1;
                        end
                    end
                end else if (saved_awaddr==16'h0004) begin
                    case(command_mask)
                        0:begin end // 零strobe为无副作用写，不产生命令。
                        1:if(state==IDLE && valid_words==1024) begin
                            state<=RUN;sequence<=sequence+1'b1;cycles<=0;error_code<=0;
                            input_count<=0;output_count<=0;image_valid<=0;feed_phase<=0;
                        end else bresp<=2;
                        2:if(state==DONE) begin
                            state<=IDLE;valid_words<=0;input_valid_map<=0;
                        end else if(state==ERROR) begin state<=RESETTING;reset_count<=0;end
                        else bresp<=2;
                        4:begin state<=RESETTING;reset_count<=0;image_valid<=0;end
                        default:bresp<=2;
                    endcase
                end else bresp<=2;
            end
        end
    end
endmodule
