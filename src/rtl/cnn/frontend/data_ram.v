`timescale 1ns/1ps
// 集成派生版：复位在计算时钟边沿生效，避免异步控制驱动RAM/DSP。
module data_ram (
    input wire sclk                             ,
    input wire s_rst_n                          ,

    input  [7:0]image_data                      ,
    input  image_data_valid                     ,
    input state_chang_flag                      ,

   //conv cal 
    input  [6:0] data_rd_addr                    ,//横向滑动66次
    input  [5:0] conv_row_cnt                    ,//纵向滑动63/31/15次
    input  [2:0] state                           ,//输入状态
    output reg [23:0] col_data                  ,//8位宽数据，一次传3个
    output reg  cal_start                       ,
    input        IN_CNT_DONE
    //pool
   // input [7:0] pool_data                       ,
    //input       pool_data_vld                   
    //input       conv_in_cnt                     ,
    //input       conv_out_cnt                    ,
)                                               ;

reg [5:0]                   data_rd_addr_padd   ;//填充所用
reg  [527:0]                rd_data_padd        ;//填充所用
wire [5:0]                  wr_addr             ;//写地址，横向滑动64次
reg  [63:0]                 wr_en               ;//一行用一位使能，64行
wire [511:0]                rd_data             ;//512=64*8位宽数据
reg  [5:0]                  col_cnt             ;
reg  [5:0]                  row_cnt             ;



localparam FIRST = 3'b001                                       ;
localparam SECOND = 3'b010                                      ;
localparam THIRD = 3'b100                                       ;

wire   state_first                                              ;
wire   state_second                                             ;
wire   state_third                                              ;
wire   ROW_CNT_DONE                                             ;  
wire   COL_CNT_DONE                                             ;
//wire   OUT_CNT_DONE                                             ;  
wire   COL_PAD                                             ;

assign state_first = (state == FIRST)                           ;
assign state_second = (state == SECOND)                         ;
assign state_third = (state == THIRD)                           ;

//wire   valid_top                                                ;
//wire [7:0] image_top                                            ;                

//assign   valid_top = image_data_valid || pool_data_vld          ;
//assign   image_top = (image_data_valid && image_data) 
                   // || ((pool_data_vld) && pool_data)         ;

assign ROW_CNT_DONE =(state_first && row_cnt == 6'd63) 
                    || (state_second && row_cnt == 6'd31) 
                    || (state_third && row_cnt == 6'd15)                        ;

assign COL_CNT_DONE =(state_first && col_cnt == 6'd63) 
                    || (state_second && col_cnt == 6'd31) 
                    || (state_third && col_cnt == 6'd15)                        ;

assign COL_PAD      =((state_first && data_rd_addr <= 7'd65) 
                    || (state_second && data_rd_addr <= 7'd33) 
                    || (state_third && data_rd_addr <= 7'd16))&&(data_rd_addr >= 7'd2); 

/*assign OUT_CNT_DONE =(state_first && conv_out_cnt == 7'd23) 
                    || (state_second && conv_out_cnt == 7'd47)                  ;
 */                   


///////////////////////////////////////////////////////////////////////////////////////////
////////FIRST态
///////////////////////////////////////////////////////////////////////////////////////////

always @(posedge sclk) begin
    if (!s_rst_n) begin
        col_cnt <= 6'd0;
    end 
    else if (COL_CNT_DONE &&image_data_valid) begin
        col_cnt <= 6'd0;
    end 
    else if (image_data_valid) begin
        col_cnt <= col_cnt + 6'b1;
    end
end

always @(posedge sclk) begin
    if (!s_rst_n) begin
        row_cnt <= 6'd0;
    end 
    else if(ROW_CNT_DONE && COL_CNT_DONE && image_data_valid)begin
        row_cnt <= 6'd0;
    end
    else if(COL_CNT_DONE && image_data_valid) begin
        row_cnt <= row_cnt + 6'b1;
    end
end


////////////////////////////////////////////////////////////////////////////////////////////

assign   wr_addr  = col_cnt                                                 ;//64/32/16

integer i                                       ;
always@(*)begin
        for(i=0;i<=63;i=i+1) begin
            if(row_cnt==i)begin
                wr_en[i]=   image_data_valid     ;
            end
            else begin
                wr_en[i]=   1'b0                ;
            end
        end
end
                                               
always @(*)begin
    case(conv_row_cnt)//每次传出一列三行数据
    6'd0:       col_data       =     rd_data_padd[23:0]  ;
    6'd1:       col_data       =     rd_data_padd[31:8]  ;
    6'd2:       col_data       =     rd_data_padd[39:16]  ;
    6'd3:       col_data       =     rd_data_padd[47:24]  ;
    6'd4:       col_data       =     rd_data_padd[55:32]  ;
    6'd5:       col_data       =     rd_data_padd[63:40]  ;
    6'd6:       col_data       =     rd_data_padd[71:48]  ;
    6'd7:       col_data       =     rd_data_padd[79:56]  ;
    6'd8:       col_data       =     rd_data_padd[87:64]  ;
    6'd9:       col_data       =     rd_data_padd[95:72]  ;
    6'd10:      col_data       =     rd_data_padd[103:80]  ;
    6'd11:      col_data       =     rd_data_padd[111:88]  ;
    6'd12:      col_data       =     rd_data_padd[119:96]  ;
    6'd13:      col_data       =     rd_data_padd[127:104]  ;
    6'd14:      col_data       =     rd_data_padd[135:112]  ;
    6'd15:      col_data       =     rd_data_padd[143:120]  ;
    6'd16:      col_data       =     rd_data_padd[151:128]  ;
    6'd17:      col_data       =     rd_data_padd[159:136]  ;
    6'd18:      col_data       =     rd_data_padd[167:144]  ;
    6'd19:      col_data       =     rd_data_padd[175:152]  ;
    6'd20:      col_data       =     rd_data_padd[183:160]  ;
    6'd21:      col_data       =     rd_data_padd[191:168]  ;
    6'd22:      col_data       =     rd_data_padd[199:176]  ;
    6'd23:      col_data       =     rd_data_padd[207:184]  ;
    6'd24:      col_data       =     rd_data_padd[215:192]  ;
    6'd25:      col_data       =     rd_data_padd[223:200]  ;
    6'd26:      col_data       =     rd_data_padd[231:208]  ;
    6'd27:      col_data       =     rd_data_padd[239:216]  ;
    6'd28:      col_data       =     rd_data_padd[247:224]  ;
    6'd29:      col_data       =     rd_data_padd[255:232]  ;
    6'd30:      col_data       =     rd_data_padd[263:240]  ;
    6'd31:      col_data       =     rd_data_padd[271:248]  ;
    6'd32:      col_data       =     rd_data_padd[279:256]  ;
    6'd33:      col_data       =     rd_data_padd[287:264]  ;
    6'd34:      col_data       =     rd_data_padd[295:272]  ;
    6'd35:      col_data       =     rd_data_padd[303:280]  ;
    6'd36:      col_data       =     rd_data_padd[311:288]  ;
    6'd37:      col_data       =     rd_data_padd[319:296]  ;
    6'd38:      col_data       =     rd_data_padd[327:304]  ;
    6'd39:      col_data       =     rd_data_padd[335:312]  ;
    6'd40:      col_data       =     rd_data_padd[343:320]  ;
    6'd41:      col_data       =     rd_data_padd[351:328]  ;
    6'd42:      col_data       =     rd_data_padd[359:336]  ;
    6'd43:      col_data       =     rd_data_padd[367:344]  ;
    6'd44:      col_data       =     rd_data_padd[375:352]  ;
    6'd45:      col_data       =     rd_data_padd[383:360]  ;
    6'd46:      col_data       =     rd_data_padd[391:368]  ;
    6'd47:      col_data       =     rd_data_padd[399:376]  ;
    6'd48:      col_data       =     rd_data_padd[407:384]  ;
    6'd49:      col_data       =     rd_data_padd[415:392]  ;
    6'd50:      col_data       =     rd_data_padd[423:400]  ;
    6'd51:      col_data       =     rd_data_padd[431:408]  ;
    6'd52:      col_data       =     rd_data_padd[439:416]  ;
    6'd53:      col_data       =     rd_data_padd[447:424]  ;
    6'd54:      col_data       =     rd_data_padd[455:432]  ;
    6'd55:      col_data       =     rd_data_padd[463:440]  ;
    6'd56:      col_data       =     rd_data_padd[471:448]  ;
    6'd57:      col_data       =     rd_data_padd[479:456]  ;
    6'd58:      col_data       =     rd_data_padd[487:464]  ;
    6'd59:      col_data       =     rd_data_padd[495:472]  ;
    6'd60:      col_data       =     rd_data_padd[503:480]  ;
    6'd61:      col_data       =     rd_data_padd[511:488]  ;
    6'd62:      col_data       =     rd_data_padd[519:496]  ;
    6'd63:      col_data       =     rd_data_padd[527:504]  ;
    default:    col_data       =     24'd0                  ;
endcase
end

always @(posedge sclk) begin
    if (!s_rst_n) begin
        cal_start <= 1'b0;
    end 
    else if ((image_data_valid && COL_CNT_DONE && ROW_CNT_DONE)
              || (state_first && IN_CNT_DONE) ) begin
        cal_start <= 1'b1;//当且仅当存储完成才启动计算
    end 
    else begin
        cal_start <= 1'b0;
    end
end


always @(*) begin
     rd_data_padd = 528'd0                                       ;
        if(COL_PAD) begin
            case(state)
                FIRST:  rd_data_padd = {8'd0,rd_data,8'd0}              ;
                SECOND: rd_data_padd[271:0] = {8'd0,rd_data[255:0],8'd0};
                THIRD:  rd_data_padd[143:0] = {8'd0,rd_data[127:0],8'd0};
                default: rd_data_padd = 528'd0                          ;
            endcase
        end
        else begin
            rd_data_padd = 528'd0                                       ;
        end
    end

always @(posedge sclk )begin
    if(!s_rst_n)begin
        data_rd_addr_padd <= 6'd0                                      ;
    end
    else if(data_rd_addr>=7'd0 && data_rd_addr<=7'd63)begin
        data_rd_addr_padd <= data_rd_addr                               ;
    end 
    else begin
        data_rd_addr_padd <= 6'd0                                       ;
    end 
end

//以行的形式存储
genvar j                                                                ;
generate
    for(j=0;j<64;j=j+1) begin
        image_data_ram image_data_ram_inst(
            .clka(sclk),    // input wire clka
            .wea(wr_en[j]),      // input wire [0 : 0] wea
            .addra(wr_addr),  // input wire [5 : 0] addra
            .dina(image_data),    // input wire [7 : 0] dina
            .clkb(sclk),    // input wire clkb
            // 空闲/装图时关闭无意义读，避免同址读写告警。
            // 地址 1 读取第 0 列；地址 2 时数据与现有 COL_PAD 对齐。
            .enb(data_rd_addr != 7'd0),
            .addrb(data_rd_addr_padd),  // input wire [5 : 0] addrb
            .doutb(rd_data[j*8+7:j*8])  // output wire [7 : 0] doutb
        )                                                               ;
    end
endgenerate












endmodule


//=============================================================================
//  模块名  : pool1_feature_cache
//  功能    : 保存完整的 24×32×32、8 位 Pool1 特征图，供 Conv2 重复读取。
//  存储组织: g = IC×32 + Y，bank = g%3，addr = (g/3)×32 + X。
//            三个 bank 各为 8192×8 bit；同一通道的三条相邻行可同时读取。
//  安全约束: 写满 24576 个像素后置 frame_ready；读取期间整份缓存只读。
//            frame_release / frame_start 仅清控制寄存器，不逐地址清 RAM。
//=============================================================================

module pool1_feature_cache (

        input                   sclk                            ,
        input                   s_rst_n                         ,

        input                   frame_start                     ,
        input                   frame_release                   ,

        input       [7:0]       wr_data                         ,
        input                   wr_valid                        ,

        output reg              channel_done                    ,
        output reg              frame_ready                     ,

        input                   rd_en                           ,
        input       [4:0]       rd_ic                           ,
        input       [4:0]       rd_row                          ,
        input       [5:0]       rd_col                          ,

        output                  rd_valid                        ,
        output      [23:0]      col_data                        ,
        output reg  [4:0]       response_row                    ,
        output reg  [5:0]       response_col
);


    //-------------------------------------------------------------------------
    //  写入按逻辑 CHW 顺序计数；物理地址再转换成三银行布局。
    //-------------------------------------------------------------------------

    reg         [4:0]       wr_ic                               ;
    reg         [4:0]       wr_row                              ;
    reg         [4:0]       wr_col                              ;

    wire        [9:0]       wr_global_row                       ;
    wire        [1:0]       wr_bank                             ;
    wire        [12:0]      wr_addr                             ;
    wire                    write_accept                        ;

    assign wr_global_row = {wr_ic, wr_row}                       ;
    assign wr_bank       = wr_global_row % 3                    ;
    assign wr_addr       = (wr_global_row / 3) * 32 + wr_col     ;

    assign write_accept  = wr_valid
                         && !frame_ready
                         && !frame_start
                         && !frame_release                      ;


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            wr_ic        <= 5'd0                                ;
            wr_row       <= 5'd0                                ;
            wr_col       <= 5'd0                                ;

            channel_done <= 1'b0                                ;
            frame_ready  <= 1'b0                                ;
        end
        else if (frame_start || frame_release) begin
            wr_ic        <= 5'd0                                ;
            wr_row       <= 5'd0                                ;
            wr_col       <= 5'd0                                ;

            channel_done <= 1'b0                                ;
            frame_ready  <= 1'b0                                ;
        end
        else begin
            channel_done <= 1'b0                                ;

            if (write_accept) begin
                if (wr_col == 5'd31) begin
                    wr_col <= 5'd0                              ;

                    if (wr_row == 5'd31) begin
                        wr_row       <= 5'd0                    ;
                        channel_done <= 1'b1                    ;

                        if (wr_ic == 5'd23) begin
                            wr_ic       <= 5'd0                 ;
                            frame_ready <= 1'b1                 ;
                        end
                        else begin
                            wr_ic <= wr_ic + 5'd1                ;
                        end
                    end
                    else begin
                        wr_row <= wr_row + 5'd1                  ;
                    end
                end
                else begin
                    wr_col <= wr_col + 5'd1                      ;
                end
            end
        end
    end


    //-------------------------------------------------------------------------
    //  rd_col=0 是左零列，1..32 对应 X=0..31，33 是右零列。
    //  先判断行是否越界，再决定是否发 RAM 读请求。
    //  顶/底填充绝不能借用前后输入通道的数据。
    //-------------------------------------------------------------------------

    wire        [9:0]       middle_global_row                   ;
    wire        [9:0]       top_global_row                      ;
    wire        [9:0]       bottom_global_row                   ;

    wire        [1:0]       top_bank                            ;
    wire        [1:0]       middle_bank                         ;
    wire        [1:0]       bottom_bank                         ;

    wire        [12:0]      top_addr                            ;
    wire        [12:0]      middle_addr                         ;
    wire        [12:0]      bottom_addr                         ;

    wire                    request_accept                      ;
    wire                    real_column                         ;
    wire                    top_valid                           ;
    wire                    middle_valid                        ;
    wire                    bottom_valid                        ;

    assign middle_global_row = {rd_ic, rd_row}                  ;
    assign top_global_row    = middle_global_row - 10'd1        ;
    assign bottom_global_row = middle_global_row + 10'd1        ;

    assign top_bank          = top_global_row    % 3            ;
    assign middle_bank       = middle_global_row % 3            ;
    assign bottom_bank       = bottom_global_row % 3            ;

    assign top_addr          = (top_global_row    / 3) * 32
                             + rd_col - 1                       ;
    assign middle_addr       = (middle_global_row / 3) * 32
                             + rd_col - 1                       ;
    assign bottom_addr       = (bottom_global_row / 3) * 32
                             + rd_col - 1                       ;

    assign request_accept    = rd_en
                             && frame_ready
                             && !frame_release                  ;

    assign real_column       = (rd_col >= 6'd1)
                             && (rd_col <= 6'd32)               ;

    assign top_valid         = real_column && (rd_row != 5'd0)  ;
    assign middle_valid      = real_column                      ;
    assign bottom_valid      = real_column && (rd_row != 5'd31) ;


    //-------------------------------------------------------------------------
    //  同步读 RAM 的输出为一拍延迟；银行选择、填充和坐标同样延迟一拍。
    //-------------------------------------------------------------------------

    wire        [23:0]      bank_data                           ;

    reg                     request_valid_d                     ;
    reg         [1:0]       top_bank_d                          ;
    reg         [1:0]       middle_bank_d                       ;
    reg         [1:0]       bottom_bank_d                       ;

    reg                     top_valid_d                         ;
    reg                     middle_valid_d                      ;
    reg                     bottom_valid_d                      ;


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            request_valid_d <= 1'b0                              ;

            top_bank_d      <= 2'd0                              ;
            middle_bank_d   <= 2'd0                              ;
            bottom_bank_d   <= 2'd0                              ;

            top_valid_d     <= 1'b0                              ;
            middle_valid_d  <= 1'b0                              ;
            bottom_valid_d  <= 1'b0                              ;

            response_row    <= 5'd0                              ;
            response_col    <= 6'd0                              ;
        end
        else begin
            request_valid_d <= request_accept                    ;

            if (request_accept) begin
                top_bank_d     <= top_bank                       ;
                middle_bank_d  <= middle_bank                    ;
                bottom_bank_d  <= bottom_bank                    ;

                top_valid_d    <= top_valid                      ;
                middle_valid_d <= middle_valid                   ;
                bottom_valid_d <= bottom_valid                   ;

                response_row   <= rd_row                         ;
                response_col   <= rd_col                         ;
            end
        end
    end


    assign rd_valid = request_valid_d && frame_ready             ;

    assign col_data[7:0] = (rd_valid && top_valid_d)
                         ? bank_data[top_bank_d * 8 +: 8]
                         : 8'd0                                 ;

    assign col_data[15:8] = (rd_valid && middle_valid_d)
                          ? bank_data[middle_bank_d * 8 +: 8]
                          : 8'd0                                ;

    assign col_data[23:16] = (rd_valid && bottom_valid_d)
                           ? bank_data[bottom_bank_d * 8 +: 8]
                           : 8'd0                               ;


    genvar bank_index                                         ;

    generate
        for (bank_index = 0; bank_index < 3; bank_index = bank_index + 1) begin : g_bank

            (* ram_style = "block" *)
            reg         [7:0]       memory [0:8191]              ;

            reg         [7:0]       read_data                    ;
            wire                    bank_read_en                 ;
            wire        [12:0]      bank_read_addr               ;

            assign bank_read_en = request_accept
                                && ((top_valid    && top_bank    == bank_index)
                                 || (middle_valid && middle_bank == bank_index)
                                 || (bottom_valid && bottom_bank == bank_index));

            assign bank_read_addr = (top_valid && top_bank == bank_index)
                                  ? top_addr
                                  : (middle_valid && middle_bank == bank_index)
                                  ? middle_addr
                                  : bottom_addr                 ;


            // RAM 本体不复位，避免被推断成大量寄存器。
            always @(posedge sclk) begin
                if (write_accept && wr_bank == bank_index) begin
                    memory[wr_addr] <= wr_data                   ;
                end

                if (bank_read_en) begin
                    read_data <= memory[bank_read_addr]         ;
                end
            end


            assign bank_data[bank_index * 8 +: 8] = read_data    ;

        end
    endgenerate

endmodule
