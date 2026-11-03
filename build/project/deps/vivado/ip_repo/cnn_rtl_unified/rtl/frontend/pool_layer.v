`timescale 1ns/1ps
// 集成派生版：复位在计算时钟边沿生效，避免异步控制驱动RAM/DSP。
//=============================================================================
//  模块名  : pool_layer
//  功能    : 2×2、stride=2 的最大池化；只对 act_data_vld=1 的像素计数。
//  尺寸    : FIRST:64×64 -> 32×32；SECOND:32×32 -> 16×16。
//  IP约束  : fifo_generator_0 使用 FWFT 模式，上行横向最大值可在读拍比较。
//  计数    : 每收到一张完整输入图就产生 channel_done；池化不计卷积 IC。
//=============================================================================

module pool_layer #(

        // 并行 Conv2 的每一路一帧产生 48/LANES 张图；0 使用各层默认值。
        parameter integer       CHANNELS_OVERRIDE = 0
) (
        input                   sclk                            ,
        input                   s_rst_n                         ,

        input       [7:0]       act_data                        ,
        input                   act_data_vld                    ,
        input       [2:0]       state                           ,
        input                   cal_start                       ,

        output reg              state_change_flag               ,
        output reg              channel_done                    ,
        output reg  [7:0]       pool_data                       ,
        output reg              pool_data_vld
);


    localparam [2:0]    FIRST  = 3'b001                          ;
    localparam [2:0]    SECOND = 3'b010                          ;
    localparam [2:0]    THIRD  = 3'b100                          ;

    wire                    state_first                         ;
    wire                    state_second                        ;
    wire                    state_third                         ;

    reg         [5:0]       col_cnt                             ;
    reg         [5:0]       row_cnt                             ;
    reg         [6:0]       conv_out_cnt                        ;

    wire                    COL_CNT_DONE                        ;
    wire                    ROW_CNT_DONE                        ;
    wire                    OUT_CNT_DONE                        ;
    wire                    map_complete                        ;


    assign state_first  = (state == FIRST)                       ;
    assign state_second = (state == SECOND)                      ;
    assign state_third  = (state == THIRD)                       ;

    assign COL_CNT_DONE = (state_first  && col_cnt == 6'd63)
                        || (state_second && col_cnt == 6'd31)
                        || (state_third  && col_cnt == 6'd15)    ;

    assign ROW_CNT_DONE = (state_first  && row_cnt == 6'd63)
                        || (state_second && row_cnt == 6'd31)
                        || (state_third  && row_cnt == 6'd15)    ;

    assign OUT_CNT_DONE = (CHANNELS_OVERRIDE != 0)
                        ? (conv_out_cnt == CHANNELS_OVERRIDE - 1)
                        : ((state_first  && conv_out_cnt == 7'd23)
                        || (state_second && conv_out_cnt == 7'd47)
                        || (state_third  && conv_out_cnt == 7'd95));

    assign map_complete = act_data_vld
                        && COL_CNT_DONE
                        && ROW_CNT_DONE                         ;


    //-------------------------------------------------------------------------
    //  坐标只在有效输入拍递增。完成标志与最后一个 pool_data 同拍。
    //-------------------------------------------------------------------------

    always @(posedge sclk) begin
        if (!s_rst_n) begin
            col_cnt           <= 6'd0                           ;
            row_cnt           <= 6'd0                           ;
            conv_out_cnt      <= 7'd0                           ;

            channel_done      <= 1'b0                           ;
            state_change_flag <= 1'b0                           ;
        end
        else begin
            channel_done      <= map_complete                   ;
            state_change_flag <= map_complete && OUT_CNT_DONE   ;

            if (act_data_vld) begin
                if (COL_CNT_DONE) begin
                    col_cnt <= 6'd0                              ;

                    if (ROW_CNT_DONE) begin
                        row_cnt <= 6'd0                          ;

                        if (OUT_CNT_DONE) begin
                            conv_out_cnt <= 7'd0                 ;
                        end
                        else begin
                            conv_out_cnt <= conv_out_cnt + 7'd1 ;
                        end
                    end
                    else begin
                        row_cnt <= row_cnt + 6'd1                ;
                    end
                end
                else begin
                    col_cnt <= col_cnt + 6'd1                    ;
                end
            end
        end
    end


    //-------------------------------------------------------------------------
    //  偶数行：两两横向取最大值后存 FIFO。
    //  奇数行：偶数列先比较 FIFO 头与当前像素；奇数列再加入右侧像素。
    //  输入有空拍时，左侧像素必须保持，不能被无效 act_data 覆盖。
    //-------------------------------------------------------------------------

    reg         [7:0]       act_data_rl                         ;
    reg         [7:0]       fifo_wr_data                        ;
    reg                     fifo_wr_en                          ;

    wire        [7:0]       fifo_rd_data                        ;
    wire                    fifo_rd_en                          ;
    reg         [7:0]       max_data                            ;


    assign fifo_rd_en = act_data_vld && row_cnt[0] && !col_cnt[0];


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            act_data_rl <= 8'd0                                  ;
        end
        else if (act_data_vld) begin
            act_data_rl <= act_data                              ;
        end
    end


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            fifo_wr_data <= 8'd0                                 ;
            fifo_wr_en   <= 1'b0                                ;
        end
        else begin
            fifo_wr_en <= 1'b0                                  ;

            if (act_data_vld && !row_cnt[0] && col_cnt[0]) begin
                fifo_wr_en <= 1'b1                               ;

                if (act_data_rl > act_data) begin
                    fifo_wr_data <= act_data_rl                 ;
                end
                else begin
                    fifo_wr_data <= act_data                    ;
                end
            end
        end
    end


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            max_data <= 8'd0                                     ;
        end
        else if (fifo_rd_en) begin
            if (fifo_rd_data > act_data) begin
                max_data <= fifo_rd_data                         ;
            end
            else begin
                max_data <= act_data                             ;
            end
        end
    end


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            pool_data     <= 8'd0                                ;
            pool_data_vld <= 1'b0                                ;
        end
        else begin
            pool_data_vld <= 1'b0                                ;

            if (act_data_vld && row_cnt[0] && col_cnt[0]) begin
                pool_data_vld <= 1'b1                             ;

                if (max_data > act_data) begin
                    pool_data <= max_data                        ;
                end
                else begin
                    pool_data <= act_data                        ;
                end
            end
        end
    end


    fifo_generator_0 fifo_generator_0_inst (

        .clk                    (sclk)                          ,
        .srst                   (~s_rst_n | cal_start)          ,

        .din                    (fifo_wr_data)                  ,
        .wr_en                  (fifo_wr_en)                    ,
        .rd_en                  (fifo_rd_en)                    ,
        .dout                   (fifo_rd_data)                  ,

        .full                   ()                              ,
        .empty                  ()
    );

endmodule



//=============================================================================
//  模块名  : pool2_channel_serializer
//  功能    : 同时接收 LANES 路 16×16 Pool2 结果，再按 CHW 顺序串行输出。
//  存储    : 一个地址保存同一空间位置的所有输出通道，宽度为 LANES×8。
//            例如两路时，每个字是 {OC1像素, OC0像素}，只需要一份写端口。
//  安全    : 收齐 256 个字后才读；最后一个字节输出后才允许启动下一组。
//            顶层必须等待 group_done，不能在串行输出期间覆盖此缓冲。
//=============================================================================

module pool2_channel_serializer #(

        parameter integer       LANES = 2
) (
        input                   sclk                            ,
        input                   s_rst_n                         ,

        input                   group_start                     ,
        input       [LANES*8-1:0] lane_data                      ,
        input       [LANES-1:0] lane_valid                       ,

        output                  group_ready                     ,
        output reg              group_done                      ,

        output reg  [7:0]       pool_data                       ,
        output reg              pool_data_vld
);


    localparam integer LANE_WIDTH = (LANES > 1) ? $clog2(LANES) : 1;

    localparam              COLLECT = 1'b0                     ;
    localparam              OUTPUT  = 1'b1                     ;

    reg                     phase                               ;
    reg         [7:0]       wr_addr                             ;

    reg         [7:0]       rd_addr                             ;
    reg         [LANE_WIDTH-1:0] rd_lane                          ;
    reg                     issue_active                        ;

    reg         [LANE_WIDTH-1:0] rd_lane_d                        ;
    reg                     rd_valid_d                          ;
    reg                     rd_last_d                           ;

    (* ram_style = "block" *)
    reg         [LANES*8-1:0] memory [0:255]                     ;

    reg         [LANES*8-1:0] read_data                          ;

    wire                    vector_valid                        ;
    wire                    issue_read                          ;

    assign vector_valid = &lane_valid                           ;
    assign issue_read   = (phase == OUTPUT) && issue_active      ;
    assign group_ready  = (phase == COLLECT) && (wr_addr == 8'd0);


    // RAM 一拍同步读，valid/lane/last 使用同样的一拍标签。
    // 控制复位不清 RAM：整组数据总是在读之前完整覆盖。
    always @(posedge sclk) begin
        if (phase == COLLECT && vector_valid && !group_start) begin
            memory[wr_addr] <= lane_data                         ;
        end

        if (issue_read) begin
            read_data <= memory[rd_addr]                        ;
        end
    end


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            phase         <= COLLECT                            ;
            wr_addr       <= 8'd0                               ;

            rd_addr       <= 8'd0                               ;
            rd_lane       <= 0                                  ;
            issue_active  <= 1'b0                               ;

            rd_lane_d     <= 0                                  ;
            rd_valid_d    <= 1'b0                               ;
            rd_last_d     <= 1'b0                               ;

            pool_data     <= 8'd0                               ;
            pool_data_vld <= 1'b0                               ;
            group_done    <= 1'b0                               ;
        end
        else if (group_start) begin
            phase         <= COLLECT                            ;
            wr_addr       <= 8'd0                               ;

            rd_addr       <= 8'd0                               ;
            rd_lane       <= 0                                  ;
            issue_active  <= 1'b0                               ;

            rd_valid_d    <= 1'b0                               ;
            rd_last_d     <= 1'b0                               ;

            pool_data_vld <= 1'b0                               ;
            group_done    <= 1'b0                               ;
        end
        else begin
            group_done    <= 1'b0                               ;
            pool_data_vld <= rd_valid_d                         ;

            rd_valid_d    <= issue_read                         ;
            rd_last_d     <= issue_read
                          && (rd_addr == 8'd255)
                          && (rd_lane == LANES - 1)             ;

            if (issue_read) begin
                rd_lane_d <= rd_lane                             ;

                if (rd_addr == 8'd255) begin
                    rd_addr <= 8'd0                              ;

                    if (rd_lane == LANES - 1) begin
                        issue_active <= 1'b0                    ;
                    end
                    else begin
                        rd_lane <= rd_lane + 1'b1               ;
                    end
                end
                else begin
                    rd_addr <= rd_addr + 8'd1                    ;
                end
            end

            if (rd_valid_d) begin
                pool_data <= read_data[rd_lane_d * 8 +: 8]        ;

                if (rd_last_d) begin
                    group_done <= 1'b1                          ;
                    phase      <= COLLECT                       ;
                    wr_addr    <= 8'd0                           ;
                end
            end

            if (phase == COLLECT && vector_valid) begin
                if (wr_addr == 8'd255) begin
                    phase        <= OUTPUT                      ;
                    rd_addr      <= 8'd0                        ;
                    rd_lane      <= 0                           ;
                    issue_active <= 1'b1                        ;
                end
                else begin
                    wr_addr <= wr_addr + 8'd1                    ;
                end
            end
        end
    end


    // 两/四路的时序必须一致，不能只收其中一路后静默丢失其他路。
    // synthesis translate_off
    always @(posedge sclk) begin
        if (s_rst_n) begin
            if ((|lane_valid) && !(&lane_valid)) begin
                $fatal(1, "Pool2 lane valid signals are not aligned");
            end

            if (phase == OUTPUT && (|lane_valid)) begin
                $fatal(1, "Pool2 output buffer overwritten before serialization finished");
            end

            if (group_start && !group_ready) begin
                $fatal(1, "A new output group started before its buffer was free");
            end
        end
    end
    // synthesis translate_on

endmodule
