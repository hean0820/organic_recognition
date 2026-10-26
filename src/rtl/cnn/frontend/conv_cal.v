`timescale 1ns/1ps
// 集成派生版：复位在计算时钟边沿生效，避免异步控制驱动RAM/DSP。
//=============================================================================
//  Conv1 保留原九路乘法 IP 和输入窗口；Conv2 并行模块附在此文件下方。
//  权重/输入 RAM/乘法 IP 延迟均为一拍；输出数据尺寸保持 24×64×64。
//=============================================================================

module  conv_cal #(
        parameter                   W_WIDTH = 8                 ,
        parameter                   B_WIDTH = 32
) 
(
    //system singals
        input wire                  sclk                        ,
        input wire                  s_rst_n                     ,
     
    //DATA RAM
        output reg   [6:0]          data_rd_addr                ,//横向滑动次数  66*66/34*34/18*18 对应69/37/21
        output reg   [5:0]          row_cnt                     ,//纵向滑动次数  63/31/15
        input wire   [23:0]         col_data                    ,//8位宽数据，一次传3个
        input                       cal_start                   ,//计算开始信号
        output reg                  IN_CNT_DONE                 , // replay pulse after last IC
        output reg                  channel_done                , // one IC scan, including writeback, completed
        output reg                  layer_done                  , // last OC completed 
    //PARAM ROM
        output reg   [13:0]         param_rd_addr               ,
        output reg   [6:0]          conv_out_cnt                ,//输出通道数 24/48/96
        input wire   [W_WIDTH-1:0]  param_w_h0                  ,
        input wire   [W_WIDTH-1:0]  param_w_h1                  ,
        input wire   [W_WIDTH-1:0]  param_w_h2                  ,
        input signed [B_WIDTH-1:0]  param_bias                  ,
    //pool
        output reg   signed [31:0]  conv_rslt_out               ,//输出给池化层的卷积结果 , 
        output reg                  conv_rslt_out_valid         ,
        input        [2:0]          state                     
)                                                               ;  


/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
reg                  [5:0]            conv_in_cnt                     ;//输入通道数  1/24/48

reg [2:0]                             drain_cnt                       ;
wire                                  input_last                      ;
wire                                  drain_done                      ;
wire                                  start_accept                    ;
reg                                   conv_flag                       ;//该层卷积进行标志
reg                  [W_WIDTH*3-1:0]  param_w_h0_arr                  ;//权重存储数组
reg                  [W_WIDTH*3-1:0]  param_w_h1_arr                  ;//权重存储数组
reg                  [W_WIDTH*3-1:0]  param_w_h2_arr                  ;//权重存储数组



reg                  [23:0]          col_data_r0                     ;//卷积核处理第一列数据
reg                  [23:0]          col_data_r1                     ;//卷积核处理第二列数据    
reg                  [23:0]          col_data_r2                     ;//卷积核处理第三列数据


wire      signed     [15:0]         mult00                          ; 
wire      signed     [15:0]         mult01                          ; 
wire      signed     [15:0]         mult02                          ; 
                     
wire      signed     [15:0]         mult10                          ; 
wire      signed     [15:0]         mult11                          ; 
wire      signed     [15:0]         mult12                          ; 

wire      signed     [15:0]         mult20                          ; 
wire      signed     [15:0]         mult21                          ; 
wire      signed     [15:0]         mult22                          ; 
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

localparam FIRST = 3'b001                                       ;
localparam SECOND = 3'b010                                      ;
localparam THIRD = 3'b100                                       ;

wire   state_first                                              ;
wire   state_second                                             ;
wire   state_third                                              ;

wire   ROW_CNT_DONE                                             ;  
wire   COL_CNT_DONE                                             ;
//wire   IN_CNT_DONE                                              ;
wire   OUT_CNT_DONE                                             ;  
wire   COL_CAL_DONE                                             ;

assign state_first = (state == FIRST);
assign state_second = (state == SECOND);
assign state_third = (state == THIRD);
//卷积层规格配置
assign ROW_CNT_DONE =(state_first && row_cnt == 6'd63) 
                    || (state_second && row_cnt == 6'd31) 
                    || (state_third && row_cnt == 6'd15);
assign COL_CNT_DONE =(state_first && data_rd_addr == 7'd69) 
                    || (state_second && data_rd_addr == 7'd37) 
                    || (state_third && data_rd_addr == 7'd21);
assign COL_CAL_DONE =(state_first && data_rd_addr <= 7'd68) 
                    || (state_second && data_rd_addr <= 7'd36) 
                    || (state_third && data_rd_addr <= 7'd20);
assign input_last = state_first
                    || (state_second && conv_in_cnt == 6'd23)
                    || (state_third && conv_in_cnt == 6'd47);
// 通道标签和偏置保持到原求和、写回流水线排空。
assign drain_done = (drain_cnt == 3'd1);
assign start_accept = cal_start && !conv_flag && (drain_cnt == 3'd0);
assign OUT_CNT_DONE =(state_first && conv_out_cnt == 7'd23) 
                    || (state_second && conv_out_cnt == 7'd47) 
                    || (state_third && conv_out_cnt == 7'd95);


/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// 每次启动只扫描一张图，等乘加/写回排空后再切换通道。
// 当前顶层仅将此模块用于 Conv1；Conv2 使用下方 conv2_parallel。
always @(posedge sclk) begin
    if (!s_rst_n) begin
        conv_out_cnt <= 7'd0                                        ;
        conv_in_cnt <= 6'd0                                         ;
        row_cnt <= 6'd0                                             ;
        data_rd_addr <= 7'd0                                        ;
        conv_flag <= 1'b0                                           ;
        drain_cnt <= 3'd0                                           ;
        channel_done <= 1'b0                                        ;
        layer_done <= 1'b0                                          ;
        IN_CNT_DONE <= 1'b0                                         ;
    end
    else begin
        channel_done <= 1'b0                                        ;
        layer_done <= 1'b0                                          ;
        IN_CNT_DONE <= 1'b0                                         ;

        if (start_accept) begin
            conv_flag <= 1'b1                                       ;
            row_cnt <= 6'd0                                         ;
            data_rd_addr <= 7'd0                                    ;
        end
        else if (conv_flag) begin
            if (COL_CNT_DONE) begin
                data_rd_addr <= 7'd0                                ;
                if (ROW_CNT_DONE) begin
                    row_cnt <= 6'd0                                 ;
                    conv_flag <= 1'b0                               ;
                    drain_cnt <= 3'd3                               ;
                end
                else begin
                    row_cnt <= row_cnt + 6'd1                       ;
                end
            end
            else begin
                data_rd_addr <= data_rd_addr + 7'd1                 ;
            end
        end
        else if (drain_cnt != 3'd0) begin
            drain_cnt <= drain_cnt - 3'd1                           ;

            if (drain_done) begin
                channel_done <= 1'b1                                ;

                if (input_last) begin
                    conv_in_cnt <= 6'd0                             ;

                    if (OUT_CNT_DONE) begin
                        conv_out_cnt <= 7'd0                        ;
                        layer_done <= 1'b1                          ;
                    end
                    else begin
                        conv_out_cnt <= conv_out_cnt + 7'd1         ;
                        // 保留旧模块接口；新顶层不再使用此重放请求。
                        if (state_second) begin
                            IN_CNT_DONE <= 1'b1                     ;
                        end
                    end
                end
                else begin
                    conv_in_cnt <= conv_in_cnt + 6'd1               ;
                end
            end
        end
    end
end

////////////////////////////////////////////////////////////////////////////////////////////////////////////////
always @(posedge sclk) begin//权重存储数组地址
    if(!s_rst_n)begin
        param_rd_addr    <=  14'd0                                   ;
    end
    else if(start_accept)begin
        // 每个 ROM 保存核内一行，地址顺序为 OC -> IC -> KX。
        if (state_first)
            param_rd_addr <= conv_out_cnt * 14'd3;
        else if (state_second)
            param_rd_addr <= conv_out_cnt * 14'd72 + conv_in_cnt * 14'd3;
        else
            param_rd_addr <= conv_out_cnt * 14'd144 + conv_in_cnt * 14'd3;
    end
    // 基址在启动时设置，仅递增两次得到 KX=1、2，然后保持有效末地址。
    else if(conv_flag == 1'b1 && row_cnt ==6'd0 && data_rd_addr <=7'd1)begin
        param_rd_addr    <=  param_rd_addr + 14'b1                   ;
    end
end

always @(posedge sclk) begin//三个权重存储数组
    if(!s_rst_n)begin
        param_w_h0_arr   <=  24'd0                                   ;
        param_w_h1_arr   <=  24'd0                                   ;
        param_w_h2_arr   <=  24'd0                                   ; 
    end
    else if(conv_flag && row_cnt ==6'd0 && data_rd_addr >=7'd1 && data_rd_addr <=7'd3 )begin//右移操作，把先接受的放在低位
        param_w_h0_arr   <=  {param_w_h0,param_w_h0_arr[W_WIDTH*3-1:W_WIDTH]};
        param_w_h1_arr   <=  {param_w_h1,param_w_h1_arr[W_WIDTH*3-1:W_WIDTH]};
        param_w_h2_arr   <=  {param_w_h2,param_w_h2_arr[W_WIDTH*3-1:W_WIDTH]};
    end
end

always @(posedge sclk) begin
    if(!s_rst_n)begin
        col_data_r0       <=  24'd0                                   ;
        col_data_r1       <=  24'd0                                   ;
        col_data_r2       <=  24'd0                                   ;
    end
    else begin
        col_data_r2       <=  col_data                               ;
        col_data_r1       <=  col_data_r2                            ;
        col_data_r0       <=  col_data_r1                            ;
    end
end




/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
mult_gen mult_gen_u00 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r0[7:0]),      // input wire [7 : 0] A
  .B(param_w_h0_arr[W_WIDTH-1:0]),      // input wire [7 : 0] B
  .P(mult00)      // output wire [15 : 0] P
);

mult_gen mult_gen_u01 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r1[7:0]),      // input wire [7 : 0] A
  .B(param_w_h0_arr[W_WIDTH*2-1:W_WIDTH]),      // input wire [7 : 0] B
  .P(mult01)      // output wire [15 : 0] P
);

mult_gen mult_gen_u02 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r2[7:0]),      // input wire [7 : 0] A
  .B(param_w_h0_arr[W_WIDTH*3-1:W_WIDTH*2]),      // input wire [7 : 0] B
  .P(mult02)      // output wire [15 : 0] P
);

//////////
mult_gen mult_gen_u10 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r0[15:8]),      // input wire [7 : 0] A
  .B(param_w_h1_arr[W_WIDTH-1:0]),      // input wire [7 : 0] B
  .P(mult10)      // output wire [15 : 0] P
);

mult_gen mult_gen_u11 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r1[15:8]),      // input wire [7 : 0] A
  .B(param_w_h1_arr[W_WIDTH*2-1:W_WIDTH]),      // input wire [7 : 0] B
  .P(mult11)      // output wire [15 : 0] P
);

mult_gen mult_gen_u12 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r2[15:8]),      // input wire [7 : 0] A
  .B(param_w_h1_arr[W_WIDTH*3-1:W_WIDTH*2]),      // input wire [7 : 0] B
  .P(mult12)      // output wire [15 : 0] P
);

//////////
mult_gen mult_gen_u20 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r0[23:16]),      // input wire [7 : 0] A
  .B(param_w_h2_arr[W_WIDTH-1:0]),      // input wire [7 : 0] B
  .P(mult20)      // output wire [15 : 0] P
);

mult_gen mult_gen_u21 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r1[23:16]),      // input wire [7 : 0] A
  .B(param_w_h2_arr[W_WIDTH*2-1:W_WIDTH]),      // input wire [7 : 0] B
  .P(mult21)      // output wire [15 : 0] P
);

mult_gen mult_gen_u22 (
  .CLK(sclk),  // input wire CLK
  .A(col_data_r2[23:16]),      // input wire [7 : 0] A
  .B(param_w_h2_arr[W_WIDTH*3-1:W_WIDTH*2]),      // input wire [7 : 0] B
  .P(mult22)      // output wire [15 : 0] P
);

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
reg      signed     [24:0]         conv_rslt                       ;//卷积结果
reg                                conv_rslt_valid                 ;//卷积结果有效标志

//输出结果计算
always @(posedge sclk) begin
    if(!s_rst_n)begin
        conv_rslt <=  25'b0                                                                 ;
    end
    else if(conv_flag && data_rd_addr >= 7'd5 && COL_CAL_DONE)begin
        conv_rslt <=    mult00 + mult01 + mult02 +
                        mult10 + mult11 + mult12 +
                        mult20 + mult21 + mult22                                            ;
    end 
end


always @(posedge sclk) begin
    if(!s_rst_n)begin
        conv_rslt_valid <=  1'b0                                                            ;
    end
    else if(conv_flag && data_rd_addr >= 7'd5 && COL_CAL_DONE)begin
        conv_rslt_valid <=  1'b1                                                            ;
    end
    else begin
        conv_rslt_valid <=  1'b0                                                            ;
    end
end
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
//////先将一个输入通道的卷积结果（32*32/16*16规模）保存在ram中，此时同一地址对应一个像素，等到下一个输入通道的某个地址的像素数据到来时
//////先提前三个时钟周期把该地址的像素数据读出来，放进缓存，和本次卷积结果相加后再写回去
//////读写地址相差三个周期，等到所有输入通道的卷积结果都累加完后，再输出给池化层
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
wire                        wea                                                             ;//读使能
wire                        rea                                                             ;//写使能
                      
assign wea = conv_rslt_valid 
            &&((state_second&& conv_in_cnt < 6'd23)
            ||(state_third&& conv_in_cnt < 6'd47)) ;//最后一个输入通道不再写入，直接加偏置

assign rea = (state_second&& (data_rd_addr <= 6'd35)||state_third&& (data_rd_addr <= 6'd19)) 
            && conv_flag && (data_rd_addr>=6'd3) && (conv_in_cnt > 6'd0)  ;  

reg                         wea_reg                                                    ;//延迟一拍
reg                         rea_reg                                                    ;//延迟一拍
always @(posedge sclk) begin
    if(!s_rst_n)begin
        wea_reg <=  1'b0                                                               ;
    end
    else begin
        wea_reg <=  wea                                                                ;
    end
end       
always @(posedge sclk) begin
    if(!s_rst_n)begin
        rea_reg <=  1'b0                                                               ;
    end
    else begin
        rea_reg <=  rea                                                                ;
    end
end             
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

reg                [9:0]   conv_rslt_addr_w                                                  ;//写地址   
always @(posedge sclk) begin
    if(!s_rst_n)begin
        conv_rslt_addr_w <=  10'd0                                                            ;
    end
    else if(wea && state_second)begin
        conv_rslt_addr_w <=  ({4'b0,row_cnt} << 5) + {3'b0,data_rd_addr} - 10'd6             ;
    end
    else if(wea && state_third)begin
        conv_rslt_addr_w <=  ({4'b0,row_cnt} << 4) + {3'b0,data_rd_addr} - 10'd6             ;
    end
end        

reg                [9:0]  conv_rslt_addr_r                                                   ;//读地址，提前两个时钟周期
always @(posedge sclk) begin
    if(!s_rst_n)begin
        conv_rslt_addr_r <=  10'd0                                                            ;
    end
    else if(rea && state_second)begin
        conv_rslt_addr_r <=  ({4'b0,row_cnt} << 5) + {3'b0,data_rd_addr} - 10'd3             ;
    end
    else if(rea && state_third)begin
        conv_rslt_addr_r <=  ({4'b0,row_cnt} << 4) + {3'b0,data_rd_addr} - 10'd3             ;
    end
end

wire      signed      [24:0]  data_buffer                                                      ;
reg       signed      [24:0]  data_buffer_reg                                                  ;//前一累加结果缓存   
reg       signed      [24:0]  conv_rslt_acc                                                    ;//本次累加结果

always @(posedge sclk) begin
    if(!s_rst_n)begin
        data_buffer_reg <=  25'd0                                                            ;
    end
    else begin
        data_buffer_reg <=  data_buffer                                                      ;
    end
end

always @(posedge sclk) begin
    if(!s_rst_n)begin
        conv_rslt_acc <=  25'd0                                                             ;
    end
    else if(wea) begin
        // 首个 IC 覆盖旧 RAM 内容，其余 IC 再累加。
        conv_rslt_acc <= (conv_in_cnt == 6'd0) ? conv_rslt : (data_buffer_reg + conv_rslt);
    end
end


wire     ea_out                                                                              ;
assign   ea_out=conv_rslt_valid
                &&(state_first
                ||(state_second&& conv_in_cnt == 6'd23)
                ||(state_third&& conv_in_cnt == 6'd47))                                          ;
                
    
conv_rslt_reg conv_rslt_reg_now_inst (
  .clka(sclk),    // input wire clka
  .wea(wea_reg),      // input wire [0 : 0] wea
  .addra(conv_rslt_addr_w),  // input wire [9 : 0] addra
  .dina(conv_rslt_acc),    // input wire [24 : 0] dina
  .clkb(sclk),    // input wire clkb
  .enb(rea_reg ),      // input wire enb
  .addrb(conv_rslt_addr_r),  // input wire [9 : 0] addrb
  .doutb(data_buffer)  // output wire [24 : 0] doutb
)                                                                                            ;   


always @(posedge sclk) begin//前一
    if(!s_rst_n)begin
        conv_rslt_out <=  32'd0                                                              ;
    end
    else if(ea_out)begin
        conv_rslt_out <= state_first ? (conv_rslt + param_bias)
                                     : (data_buffer_reg + conv_rslt + param_bias)                             ;
    end
end
always @(posedge sclk) begin
    if(!s_rst_n)begin
        conv_rslt_out_valid <=  1'b0                                                         ;
    end
    else if(ea_out)begin
        conv_rslt_out_valid <=  1'b1                                                         ;
    end
    else begin
        conv_rslt_out_valid <=  1'b0                                                         ;
    end
end

endmodule


//=============================================================================
//  模块名  : conv2_parallel
//  功能    : Conv2 输出通道并行；每组 LANES 路共享同一个 3×3 输入窗口。
//  网络    : 24×32×32 -> 48×32×32，3×3，stride=1，零填充。
//  调度    : 每个 IC 先加载本组的 LANES 套权重，再完整扫描 32×32。
//            IC=0 覆盖部分和；IC=1..22 累加；IC=23 加偏置并输出。
//  接口    : start 仅启动一组 OC；group_done 后仍须等待池化/串行输出完成，
//            顶层才可改变 group_oc 并启动下一组。
//  IP约束  : 权重/偏置 ROM、mult_gen、conv_rslt_reg 都采用一拍读/乘法延迟。
//=============================================================================

module conv2_parallel #(

        parameter integer       LANES = 2
) (
        input                   sclk                            ,
        input                   s_rst_n                         ,

        input                   start                           ,
        input       [5:0]       group_oc                        ,

        output                  busy                            ,
        output reg              channel_done                    ,
        output reg              group_done                      ,
        output reg  [4:0]       conv_in_cnt                     ,
        output reg  [5:0]       active_group_oc                 ,

        output      [11:0]      param_rd_addr                   ,
        output      [5:0]       bias_rd_addr                    ,
        input       [7:0]       param_w_h0                      ,
        input       [7:0]       param_w_h1                      ,
        input       [7:0]       param_w_h2                      ,
        input signed [31:0]     param_bias                      ,

        output                  cache_rd_en                     ,
        output      [4:0]       cache_rd_ic                     ,
        output reg  [4:0]       cache_rd_row                    ,
        output reg  [5:0]       cache_rd_col                    ,

        input                   cache_rd_valid                  ,
        input       [23:0]      cache_col_data                  ,
        input       [4:0]       cache_response_row              ,
        input       [5:0]       cache_response_col              ,

        output      [LANES*32-1:0] conv_rslt_out                 ,
        output      [LANES-1:0] conv_rslt_out_valid
);


    localparam integer LANE_WIDTH = (LANES > 1) ? $clog2(LANES) : 1;

    localparam [2:0]    IDLE        = 3'd0                       ;
    localparam [2:0]    LOAD_WEIGHT = 3'd1                       ;
    localparam [2:0]    WAIT_ROM    = 3'd2                       ;
    localparam [2:0]    SCAN        = 3'd3                       ;
    localparam [2:0]    DRAIN       = 3'd4                       ;

    reg         [2:0]       phase                               ;
    reg         [LANE_WIDTH-1:0] load_lane                       ;
    reg         [1:0]       load_col                            ;

    reg                     weight_valid_d                      ;
    reg         [LANE_WIDTH-1:0] load_lane_d                     ;
    reg         [1:0]       load_col_d                          ;

    reg         [LANES*24-1:0] kernel_h0                         ;
    reg         [LANES*24-1:0] kernel_h1                         ;
    reg         [LANES*24-1:0] kernel_h2                         ;
    reg         [LANES*32-1:0] bias_array                        ;

    wire        [LANES-1:0] lane_done                            ;


    // 三个 ROM 每拍提供核内同一列的上、中、下三个权重。
    // 不复制整个权重 ROM，只在扫描前保存各输出通道的九个权重。
    assign param_rd_addr = (active_group_oc + load_lane) * 72
                         + conv_in_cnt * 3
                         + load_col                             ;

    assign bias_rd_addr  = active_group_oc + load_lane           ;

    assign busy          = (phase != IDLE)                      ;
    assign cache_rd_en   = (phase == SCAN)                      ;
    assign cache_rd_ic   = conv_in_cnt                          ;


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            phase           <= IDLE                             ;

            load_lane       <= 0                                ;
            load_col        <= 2'd0                             ;
            load_lane_d     <= 0                                ;
            load_col_d      <= 2'd0                             ;
            weight_valid_d  <= 1'b0                             ;

            kernel_h0       <= 0                                ;
            kernel_h1       <= 0                                ;
            kernel_h2       <= 0                                ;
            bias_array      <= 0                                ;

            conv_in_cnt     <= 5'd0                             ;
            active_group_oc <= 6'd0                             ;
            cache_rd_row    <= 5'd0                             ;
            cache_rd_col    <= 6'd0                             ;

            channel_done    <= 1'b0                             ;
            group_done      <= 1'b0                             ;
        end
        else begin
            channel_done   <= 1'b0                              ;
            group_done     <= 1'b0                              ;
            weight_valid_d <= (phase == LOAD_WEIGHT)            ;

            if (phase == LOAD_WEIGHT) begin
                load_lane_d <= load_lane                         ;
                load_col_d  <= load_col                          ;
            end

            case (phase)

                IDLE: begin
                    if (start) begin
                        active_group_oc <= group_oc             ;
                        conv_in_cnt     <= 5'd0                 ;

                        load_lane       <= 0                    ;
                        load_col        <= 2'd0                 ;
                        phase           <= LOAD_WEIGHT          ;
                    end
                end

                LOAD_WEIGHT: begin
                    if (load_col == 2'd2) begin
                        load_col <= 2'd0                        ;

                        if (load_lane == LANES - 1) begin
                            // 最后一条请求尚未返回，不能立即开始扫描。
                            phase <= WAIT_ROM                   ;
                        end
                        else begin
                            load_lane <= load_lane + 1'b1       ;
                        end
                    end
                    else begin
                        load_col <= load_col + 2'd1             ;
                    end
                end

                WAIT_ROM: begin
                    // 返回处理在下方 weight_valid_d 分支中完成。
                end

                SCAN: begin
                    if (cache_rd_col == 6'd33) begin
                        cache_rd_col <= 6'd0                    ;

                        if (cache_rd_row == 5'd31) begin
                            // 请求发完不代表算完；继续接收 RAM 返回，
                            // 等待九路乘法、求和、累加和最后一次写回。
                            phase <= DRAIN                      ;
                        end
                        else begin
                            cache_rd_row <= cache_rd_row + 5'd1 ;
                        end
                    end
                    else begin
                        cache_rd_col <= cache_rd_col + 6'd1     ;
                    end
                end

                DRAIN: begin
                    if (&lane_done) begin
                        channel_done <= 1'b1                    ;

                        if (conv_in_cnt == 5'd23) begin
                            group_done <= 1'b1                  ;
                            phase      <= IDLE                  ;
                        end
                        else begin
                            conv_in_cnt <= conv_in_cnt + 5'd1   ;
                            load_lane   <= 0                    ;
                            load_col    <= 2'd0                 ;
                            phase       <= LOAD_WEIGHT          ;
                        end
                    end
                end

                default: begin
                    phase <= IDLE                               ;
                end

            endcase


            // ROM 数据与请求的 lane/column 使用相同的一拍标签。
            if (weight_valid_d) begin
                kernel_h0[load_lane_d * 24 + load_col_d * 8 +: 8]
                    <= param_w_h0                               ;

                kernel_h1[load_lane_d * 24 + load_col_d * 8 +: 8]
                    <= param_w_h1                               ;

                kernel_h2[load_lane_d * 24 + load_col_d * 8 +: 8]
                    <= param_w_h2                               ;

                if (load_col_d == 2'd2) begin
                    bias_array[load_lane_d * 32 +: 32]
                        <= param_bias                           ;

                    if (load_lane_d == LANES - 1) begin
                        cache_rd_row <= 5'd0                    ;
                        cache_rd_col <= 6'd0                    ;
                        phase        <= SCAN                    ;
                    end
                end
            end
        end
    end


    //-------------------------------------------------------------------------
    //  垂直三像素列拼成窗口。响应列 0 清掉上一行的历史；
    //  响应列 2..33 分别产生当前行的输出 X=0..31。
    //  window_addr 是像素标签，后续每一级都随数据延迟，避免魔数偏移。
    //-------------------------------------------------------------------------

    reg         [23:0]      window_c0                           ;
    reg         [23:0]      window_c1                           ;
    reg         [23:0]      window_c2                           ;
    reg                     window_valid                        ;
    reg         [9:0]       window_addr                         ;


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            window_c0    <= 24'd0                                ;
            window_c1    <= 24'd0                                ;
            window_c2    <= 24'd0                                ;
            window_valid <= 1'b0                                 ;
            window_addr  <= 10'd0                                ;
        end
        else begin
            window_valid <= 1'b0                                 ;

            if (cache_rd_valid) begin
                if (cache_response_col == 6'd0) begin
                    window_c0 <= 24'd0                           ;
                    window_c1 <= 24'd0                           ;
                    window_c2 <= 24'd0                           ;
                end
                else begin
                    window_c0 <= window_c1                       ;
                    window_c1 <= window_c2                       ;
                    window_c2 <= cache_col_data                  ;
                end

                if (cache_response_col >= 6'd2) begin
                    window_valid <= 1'b1                         ;
                    window_addr  <= {cache_response_row, 5'd0}
                                  + cache_response_col - 6'd2    ;
                end
            end
        end
    end


    genvar lane_index                                           ;

    generate
        for (lane_index = 0; lane_index < LANES; lane_index = lane_index + 1) begin : g_lane

            conv2_mac_lane conv2_mac_lane_inst (

                .sclk                   (sclk)                  ,
                .s_rst_n                (s_rst_n)               ,

                .window_c0              (window_c0)             ,
                .window_c1              (window_c1)             ,
                .window_c2              (window_c2)             ,
                .window_valid           (window_valid)          ,
                .window_addr            (window_addr)           ,

                .kernel_h0              (kernel_h0[lane_index * 24 +: 24]),
                .kernel_h1              (kernel_h1[lane_index * 24 +: 24]),
                .kernel_h2              (kernel_h2[lane_index * 24 +: 24]),

                .conv_in_cnt            (conv_in_cnt)            ,
                .param_bias             (bias_array[lane_index * 32 +: 32]),

                .conv_rslt_out          (conv_rslt_out[lane_index * 32 +: 32]),
                .conv_rslt_out_valid    (conv_rslt_out_valid[lane_index]),
                .channel_done           (lane_done[lane_index])
            );

        end
    endgenerate


    // 本版只支持整除 48 的 1/2/4 路配置，不改变实际输出通道数。
    // synthesis translate_off
    initial begin
        if (LANES != 1 && LANES != 2 && LANES != 4) begin
            $fatal(1, "CONV2 LANES must be 1, 2 or 4");
        end
    end
    // synthesis translate_on

endmodule


//=============================================================================
//  模块名  : conv2_mac_lane
//  功能    : 一个输出通道的九路乘法、跨 IC 累加与加偏置。
//  IP      : 保留原 mult_gen / conv_rslt_reg，不用 RTL '*' 替换卷积乘法。
//  流水线 : 窗口 -> 一拍乘法 -> 求和/读 RAM 缓存 -> 累加 -> RAM 写回。
//            每一级的 valid 和像素地址同步传递。
//=============================================================================

module conv2_mac_lane (

        input                   sclk                            ,
        input                   s_rst_n                         ,

        input       [23:0]      window_c0                       ,
        input       [23:0]      window_c1                       ,
        input       [23:0]      window_c2                       ,
        input                   window_valid                    ,
        input       [9:0]       window_addr                     ,

        input       [23:0]      kernel_h0                       ,
        input       [23:0]      kernel_h1                       ,
        input       [23:0]      kernel_h2                       ,

        input       [4:0]       conv_in_cnt                     ,
        input signed [31:0]     param_bias                      ,

        output reg signed [31:0] conv_rslt_out                   ,
        output reg              conv_rslt_out_valid             ,
        output reg              channel_done
);


    wire signed [15:0]      mult00                              ;
    wire signed [15:0]      mult01                              ;
    wire signed [15:0]      mult02                              ;

    wire signed [15:0]      mult10                              ;
    wire signed [15:0]      mult11                              ;
    wire signed [15:0]      mult12                              ;

    wire signed [15:0]      mult20                              ;
    wire signed [15:0]      mult21                              ;
    wire signed [15:0]      mult22                              ;


    mult_gen mult_gen_u00 (

        .CLK                    (sclk)                          ,
        .A                      (window_c0[0 +: 8])       ,
        .B                      (kernel_h0[0 +: 8])       ,
        .P                      (mult00)
    );


    mult_gen mult_gen_u01 (

        .CLK                    (sclk)                          ,
        .A                      (window_c1[0 +: 8])       ,
        .B                      (kernel_h0[8 +: 8])       ,
        .P                      (mult01)
    );


    mult_gen mult_gen_u02 (

        .CLK                    (sclk)                          ,
        .A                      (window_c2[0 +: 8])       ,
        .B                      (kernel_h0[16 +: 8])       ,
        .P                      (mult02)
    );


    mult_gen mult_gen_u10 (

        .CLK                    (sclk)                          ,
        .A                      (window_c0[8 +: 8])       ,
        .B                      (kernel_h1[0 +: 8])       ,
        .P                      (mult10)
    );


    mult_gen mult_gen_u11 (

        .CLK                    (sclk)                          ,
        .A                      (window_c1[8 +: 8])       ,
        .B                      (kernel_h1[8 +: 8])       ,
        .P                      (mult11)
    );


    mult_gen mult_gen_u12 (

        .CLK                    (sclk)                          ,
        .A                      (window_c2[8 +: 8])       ,
        .B                      (kernel_h1[16 +: 8])       ,
        .P                      (mult12)
    );


    mult_gen mult_gen_u20 (

        .CLK                    (sclk)                          ,
        .A                      (window_c0[16 +: 8])       ,
        .B                      (kernel_h2[0 +: 8])       ,
        .P                      (mult20)
    );


    mult_gen mult_gen_u21 (

        .CLK                    (sclk)                          ,
        .A                      (window_c1[16 +: 8])       ,
        .B                      (kernel_h2[8 +: 8])       ,
        .P                      (mult21)
    );


    mult_gen mult_gen_u22 (

        .CLK                    (sclk)                          ,
        .A                      (window_c2[16 +: 8])       ,
        .B                      (kernel_h2[16 +: 8])       ,
        .P                      (mult22)
    );



    //-------------------------------------------------------------------------
    //  部分和 RAM 只在 IC>0 时读。IC0 直接覆盖，不依赖 RAM 初值或复位。
    //-------------------------------------------------------------------------

    wire signed [24:0]      partial_data                        ;
    reg signed  [24:0]      partial_data_d                      ;

    reg                     mult_valid_d                        ;
    reg         [9:0]       mult_addr_d                         ;

    reg signed  [24:0]      sum_result                          ;
    reg                     sum_valid                           ;
    reg         [9:0]       sum_addr                            ;

    reg signed  [24:0]      accumulated_result                  ;
    reg                     write_valid                         ;
    reg         [9:0]       write_addr                          ;

    reg                     last_sum_d                          ;


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            mult_valid_d       <= 1'b0                           ;
            mult_addr_d        <= 10'd0                          ;

            sum_result         <= 25'sd0                         ;
            sum_valid          <= 1'b0                           ;
            sum_addr           <= 10'd0                          ;

            partial_data_d     <= 25'sd0                         ;
            accumulated_result <= 25'sd0                         ;
            write_valid        <= 1'b0                           ;
            write_addr         <= 10'd0                          ;

            conv_rslt_out       <= 32'sd0                        ;
            conv_rslt_out_valid <= 1'b0                          ;

            last_sum_d         <= 1'b0                           ;
            channel_done       <= 1'b0                           ;
        end
        else begin
            mult_valid_d        <= window_valid                  ;
            sum_valid           <= mult_valid_d                  ;

            write_valid         <= 1'b0                          ;
            conv_rslt_out_valid <= 1'b0                          ;

            // done 再延迟一拍；该拍最后一次 RAM 写入真正完成。
            last_sum_d          <= sum_valid && (sum_addr == 10'd1023);
            channel_done        <= last_sum_d                    ;

            partial_data_d      <= partial_data                  ;

            if (window_valid) begin
                mult_addr_d <= window_addr                       ;
            end

            if (mult_valid_d) begin
                // 每个 16 位乘积显式符号扩展成 25 位，避免求和位宽歧义。
                sum_result <= {{9{mult00[15]}}, mult00}
                            + {{9{mult01[15]}}, mult01}
                            + {{9{mult02[15]}}, mult02}
                            + {{9{mult10[15]}}, mult10}
                            + {{9{mult11[15]}}, mult11}
                            + {{9{mult12[15]}}, mult12}
                            + {{9{mult20[15]}}, mult20}
                            + {{9{mult21[15]}}, mult21}
                            + {{9{mult22[15]}}, mult22}          ;

                sum_addr <= mult_addr_d                          ;
            end

            if (sum_valid) begin
                if (conv_in_cnt == 5'd23) begin
                    conv_rslt_out <= $signed(sum_result)
                                   + $signed(partial_data_d)
                                   + param_bias                 ;

                    conv_rslt_out_valid <= 1'b1                  ;
                end
                else begin
                    if (conv_in_cnt == 5'd0) begin
                        accumulated_result <= sum_result        ;
                    end
                    else begin
                        accumulated_result <= sum_result
                                            + partial_data_d    ;
                    end

                    write_addr  <= sum_addr                     ;
                    write_valid <= 1'b1                         ;
                end
            end
        end
    end


    conv_rslt_reg conv_rslt_reg_inst (

        .clka                   (sclk)                          ,
        .wea                    (write_valid)                   ,
        .addra                  (write_addr)                    ,
        .dina                   (accumulated_result)            ,

        .clkb                   (sclk)                          ,
        .enb                    (window_valid && conv_in_cnt != 5'd0),
        .addrb                  (window_addr)                   ,
        .doutb                  (partial_data)
    );

endmodule
