// 集成派生版：复位在计算时钟边沿生效，避免异步控制驱动RAM/DSP。
//=============================================================================
//  模块名  : cnn_top
//  网络    : 1×64×64 -> Conv1(24×64×64) -> Pool1(24×32×32)
//                       -> Conv2(48×32×32) -> Pool2(48×16×16)
//  调度    : 第一层只计算一遍，完整缓存 Pool1；Conv2 每组并行计算两路 OC。
//  接口    : 输入/输出均为 CHW、X 变化最快，像素和激活数据宽度为 8。
//            新增 image_data_ready / frame_done，可连续处理多帧。
//            下游必须在 pool_data_out_vld=1 时接收输出，本版无输出反压。
//  说明    : 辅助模块位于现有 data_ram.v / conv_cal.v / pool_layer.v 内，
//            不需要向原 Vivado 工程额外添加 RTL 文件。
//=============================================================================

module cnn_top #(

        parameter integer       CONV2_LANES = 2
) (
        input                   sclk                            ,
        input                   s_rst_n                         ,

        input                   image_data_vld                  ,
        input       [7:0]       image_data                      ,

        output      [7:0]       pool_data_out                   ,
        output                  pool_data_out_vld               ,

        output                  image_data_ready                ,
        output                  frame_done
);


    //-------------------------------------------------------------------------
    //  帧级控制：装入原图 -> 生成并锁定完整 Pool1 -> 逐组计算/串行输出。
    //  整个 Conv2 阶段都不允许覆盖原图或 Pool1 特征缓存。
    //-------------------------------------------------------------------------

    localparam [1:0]    LOAD_IMAGE = 2'd0                        ;
    localparam [1:0]    BUILD_POOL1 = 2'd1                       ;
    localparam [1:0]    RUN_CONV2 = 2'd2                         ;

    reg         [1:0]       frame_phase                         ;
    reg         [11:0]      image_wr_count                      ;
    reg         [5:0]       conv2_group_oc                      ;
    reg                     conv2_group_start                   ;

    wire                    image_accept                        ;
    wire                    frame_start                         ;

    wire                    cache_channel_done                  ;
    wire                    cache_frame_ready                   ;

    wire                    output_group_ready                  ;
    wire                    output_group_done                   ;
    wire                    conv2_busy                          ;


    assign image_data_ready = (frame_phase == LOAD_IMAGE)        ;
    assign image_accept     = image_data_vld && image_data_ready ;
    assign frame_start      = image_accept && image_wr_count == 12'd0;

    // 与最后一个 Pool2 输出字节同拍，不是 Conv2 扫描结束时提前宣告完成。
    assign frame_done = output_group_done
                      && frame_phase == RUN_CONV2
                      && conv2_group_oc == 48 - CONV2_LANES      ;


    always @(posedge sclk) begin
        if (!s_rst_n) begin
            frame_phase       <= LOAD_IMAGE                     ;
            image_wr_count    <= 12'd0                          ;
            conv2_group_oc    <= 6'd0                           ;
            conv2_group_start <= 1'b0                           ;
        end
        else begin
            conv2_group_start <= 1'b0                           ;

            case (frame_phase)

                LOAD_IMAGE: begin
                    if (image_accept) begin
                        if (image_wr_count == 12'd4095) begin
                            image_wr_count <= 12'd0              ;
                            frame_phase    <= BUILD_POOL1        ;
                        end
                        else begin
                            image_wr_count <= image_wr_count + 12'd1;
                        end
                    end
                end

                BUILD_POOL1: begin
                    if (cache_frame_ready && output_group_ready) begin
                        conv2_group_oc    <= 6'd0                ;
                        conv2_group_start <= 1'b1                ;
                        frame_phase       <= RUN_CONV2          ;
                    end
                end

                RUN_CONV2: begin
                    if (output_group_done) begin
                        if (conv2_group_oc == 48 - CONV2_LANES) begin
                            conv2_group_oc <= 6'd0               ;
                            frame_phase    <= LOAD_IMAGE         ;
                        end
                        else begin
                            // 等待上一组 Pool2 串行输出完，缓冲区才可复用。
                            conv2_group_oc    <= conv2_group_oc + CONV2_LANES;
                            conv2_group_start <= 1'b1            ;
                        end
                    end
                end

                default: begin
                    frame_phase <= LOAD_IMAGE                    ;
                end

            endcase
        end
    end


    //-------------------------------------------------------------------------
    //  Conv1：保留原来的九路乘法、输入行 RAM 与已经修正的填充时序。
    //  下一个 OC 由 Pool1 缓存的“通道写入完成”启动，不再等待/重放 Conv2。
    //-------------------------------------------------------------------------

    wire        [6:0]       data_rd_addr_layer1                 ;
    wire        [5:0]       conv_row_cnt_layer1                 ;
    wire        [23:0]      col_data_layer1                     ;
    wire                    cal_start_layer1                    ;

    wire        [13:0]      param_rd_addr_layer1                ;
    wire        [6:0]       conv_out_cnt_layer1                 ;
    wire        [7:0]       param_w_h0_layer1                   ;
    wire        [7:0]       param_w_h1_layer1                   ;
    wire        [7:0]       param_w_h2_layer1                   ;
    wire signed [31:0]      param_bias_layer1                   ;

    wire signed [31:0]      conv_rslt_out_layer1                ;
    wire                    conv_rslt_out_valid_layer1          ;

    wire        [7:0]       conv_rslt_act_layer1                ;
    wire                    conv_rslt_act_valid_layer1          ;

    wire        [7:0]       pool_data_layer1                    ;
    wire                    pool_data_vld_layer1                ;
    wire                    state_change_flag_layer1            ;


    data_ram data_ram_layer1_inst (

        .sclk                   (sclk)                          ,
        .s_rst_n                (s_rst_n)                       ,

        .image_data             (image_data)                    ,
        .image_data_valid       (image_accept)                  ,
        .state_chang_flag       (1'b0)                          ,

        .state                  (3'b001)                        ,
        .IN_CNT_DONE            (cache_channel_done && !cache_frame_ready),

        .data_rd_addr           (data_rd_addr_layer1)           ,
        .conv_row_cnt           (conv_row_cnt_layer1)           ,
        .col_data               (col_data_layer1)               ,
        .cal_start              (cal_start_layer1)
    );


    conv_cal conv_cal_layer1_inst (

        .sclk                   (sclk)                          ,
        .s_rst_n                (s_rst_n)                       ,

        .data_rd_addr           (data_rd_addr_layer1)           ,
        .row_cnt                (conv_row_cnt_layer1)           ,
        .col_data               (col_data_layer1)               ,
        .cal_start              (cal_start_layer1)              ,

        .IN_CNT_DONE            ()                              ,
        .channel_done           ()                              ,
        .layer_done             ()                              ,

        .param_rd_addr          (param_rd_addr_layer1)          ,
        .conv_out_cnt           (conv_out_cnt_layer1)           ,

        .param_w_h0             (param_w_h0_layer1)             ,
        .param_w_h1             (param_w_h1_layer1)             ,
        .param_w_h2             (param_w_h2_layer1)             ,
        .param_bias             (param_bias_layer1)             ,

        .conv_rslt_out          (conv_rslt_out_layer1)           ,
        .conv_rslt_out_valid    (conv_rslt_out_valid_layer1)     ,
        .state                  (3'b001)
    );


    requant_relu requant_relu_layer1_inst (

        .clk                    (sclk)                          ,
        .rst_n                  (s_rst_n)                       ,

        .acc_in                 (conv_rslt_out_layer1)          ,
        .in_valid               (conv_rslt_out_valid_layer1)    ,
        .state                  (3'b001)                        ,

        .act_out                (conv_rslt_act_layer1)          ,
        .out_valid              (conv_rslt_act_valid_layer1)
    );


    pool_layer pool_layer_layer1_inst (

        .sclk                   (sclk)                          ,
        .s_rst_n                (s_rst_n)                       ,

        .act_data               (conv_rslt_act_layer1)          ,
        .act_data_vld           (conv_rslt_act_valid_layer1)     ,
        .cal_start              (cal_start_layer1)              ,
        .state                  (3'b001)                        ,

        .channel_done           ()                              ,
        .state_change_flag      (state_change_flag_layer1)      ,

        .pool_data              (pool_data_layer1)              ,
        .pool_data_vld          (pool_data_vld_layer1)
    );


    //-------------------------------------------------------------------------
    //  Pool1 完整特征缓存：24 KiB，三银行，一拍同步读。
    //-------------------------------------------------------------------------

    wire                    cache_rd_en                         ;
    wire        [4:0]       cache_rd_ic                         ;
    wire        [4:0]       cache_rd_row                        ;
    wire        [5:0]       cache_rd_col                        ;

    wire                    cache_rd_valid                      ;
    wire        [23:0]      cache_col_data                      ;
    wire        [4:0]       cache_response_row                  ;
    wire        [5:0]       cache_response_col                  ;


    pool1_feature_cache pool1_feature_cache_inst (

        .sclk                   (sclk)                          ,
        .s_rst_n                (s_rst_n)                       ,

        .frame_start            (frame_start)                   ,
        .frame_release          (frame_done)                    ,

        .wr_data                (pool_data_layer1)              ,
        .wr_valid               (pool_data_vld_layer1 && frame_phase == BUILD_POOL1),

        .channel_done           (cache_channel_done)            ,
        .frame_ready            (cache_frame_ready)             ,

        .rd_en                  (cache_rd_en)                   ,
        .rd_ic                  (cache_rd_ic)                   ,
        .rd_row                 (cache_rd_row)                  ,
        .rd_col                 (cache_rd_col)                  ,

        .rd_valid               (cache_rd_valid)                ,
        .col_data               (cache_col_data)                ,
        .response_row           (cache_response_row)            ,
        .response_col           (cache_response_col)
    );


    //-------------------------------------------------------------------------
    //  Conv2：共享窗口和权重 ROM，LANES 路独立乘法、部分和及后处理。
    //-------------------------------------------------------------------------

    wire        [11:0]      param_rd_addr_layer2                ;
    wire        [5:0]       bias_rd_addr_layer2                 ;
    wire        [7:0]       param_w_h0_layer2                   ;
    wire        [7:0]       param_w_h1_layer2                   ;
    wire        [7:0]       param_w_h2_layer2                   ;
    wire signed [31:0]      param_bias_layer2                   ;

    wire        [4:0]       conv2_in_cnt                        ;
    wire        [5:0]       conv2_active_group_oc               ;
    wire                    conv2_channel_done                  ;
    wire                    conv2_group_done                    ;

    wire        [CONV2_LANES*32-1:0] conv2_rslt_bus              ;
    wire        [CONV2_LANES-1:0] conv2_rslt_valid               ;

    wire        [CONV2_LANES*8-1:0] conv2_act_bus                ;
    wire        [CONV2_LANES-1:0] conv2_act_valid                ;

    wire        [CONV2_LANES*8-1:0] pool2_lane_data              ;
    wire        [CONV2_LANES-1:0] pool2_lane_valid               ;


    conv2_parallel #(

        .LANES                  (CONV2_LANES)
    ) conv_cal_layer2_inst (

        .sclk                   (sclk)                          ,
        .s_rst_n                (s_rst_n)                       ,

        .start                  (conv2_group_start)             ,
        .group_oc               (conv2_group_oc)                ,

        .busy                   (conv2_busy)                    ,
        .channel_done           (conv2_channel_done)            ,
        .group_done             (conv2_group_done)              ,
        .conv_in_cnt            (conv2_in_cnt)                  ,
        .active_group_oc        (conv2_active_group_oc)         ,

        .param_rd_addr          (param_rd_addr_layer2)          ,
        .bias_rd_addr           (bias_rd_addr_layer2)           ,
        .param_w_h0             (param_w_h0_layer2)             ,
        .param_w_h1             (param_w_h1_layer2)             ,
        .param_w_h2             (param_w_h2_layer2)             ,
        .param_bias             (param_bias_layer2)             ,

        .cache_rd_en            (cache_rd_en)                   ,
        .cache_rd_ic            (cache_rd_ic)                   ,
        .cache_rd_row           (cache_rd_row)                  ,
        .cache_rd_col           (cache_rd_col)                  ,

        .cache_rd_valid         (cache_rd_valid)                ,
        .cache_col_data         (cache_col_data)                ,
        .cache_response_row     (cache_response_row)            ,
        .cache_response_col     (cache_response_col)            ,

        .conv_rslt_out          (conv2_rslt_bus)                 ,
        .conv_rslt_out_valid    (conv2_rslt_valid)
    );


    genvar lane_index                                           ;

    generate
        for (lane_index = 0; lane_index < CONV2_LANES; lane_index = lane_index + 1) begin : g_conv2_post

            requant_relu requant_relu_layer2_inst (

                .clk                    (sclk)                  ,
                .rst_n                  (s_rst_n)               ,

                .acc_in                 (conv2_rslt_bus[lane_index * 32 +: 32]),
                .in_valid               (conv2_rslt_valid[lane_index]),
                .state                  (3'b010)                ,

                .act_out                (conv2_act_bus[lane_index * 8 +: 8]),
                .out_valid              (conv2_act_valid[lane_index])
            );


            pool_layer #(

                .CHANNELS_OVERRIDE      (48 / CONV2_LANES)
            ) pool_layer_layer2_inst (

                .sclk                   (sclk)                  ,
                .s_rst_n                (s_rst_n)               ,

                .act_data               (conv2_act_bus[lane_index * 8 +: 8]),
                .act_data_vld           (conv2_act_valid[lane_index]),
                .cal_start              (conv2_group_start)     ,
                .state                  (3'b010)                ,

                .channel_done           ()                      ,
                .state_change_flag      ()                      ,

                .pool_data              (pool2_lane_data[lane_index * 8 +: 8]),
                .pool_data_vld          (pool2_lane_valid[lane_index])
            );

        end
    endgenerate


    pool2_channel_serializer #(

        .LANES                  (CONV2_LANES)
    ) pool2_channel_serializer_inst (

        .sclk                   (sclk)                          ,
        .s_rst_n                (s_rst_n)                       ,

        .group_start            (conv2_group_start)             ,
        .lane_data              (pool2_lane_data)               ,
        .lane_valid             (pool2_lane_valid)              ,

        .group_ready            (output_group_ready)           ,
        .group_done             (output_group_done)             ,

        .pool_data              (pool_data_out)                 ,
        .pool_data_vld          (pool_data_out_vld)
    );


    //-------------------------------------------------------------------------
    //  原权重/偏置 ROM IP 名称保持不变。
    //  六个权重 ROM 必须使用 code/params 下按核内 KY 分行的 COE，
    //  不能再使用按完整卷积核序列切成三段的 conv_weight_rows 文件。
    //-------------------------------------------------------------------------


    rom_b_ip rom_b_layer1_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (conv_out_cnt_layer1[4:0])                       ,
        .douta                  (param_bias_layer1)
    );


    rom_w0_ip rom_w0_layer1_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (param_rd_addr_layer1[6:0]) ,
        .douta                  (param_w_h0_layer1)
    );


    rom_w1_ip rom_w1_layer1_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (param_rd_addr_layer1[6:0]) ,
        .douta                  (param_w_h1_layer1)
    );


    rom_w2_ip rom_w2_layer1_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (param_rd_addr_layer1[6:0]) ,
        .douta                  (param_w_h2_layer1)
    );


    rom_b_layer2_ip rom_b_layer2_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (bias_rd_addr_layer2)                       ,
        .douta                  (param_bias_layer2)
    );


    rom_w0_layer2_ip rom_w0_layer2_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (param_rd_addr_layer2) ,
        .douta                  (param_w_h0_layer2)
    );


    rom_w1_layer2_ip rom_w1_layer2_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (param_rd_addr_layer2) ,
        .douta                  (param_w_h1_layer2)
    );


    rom_w2_layer2_ip rom_w2_layer2_inst (

        .clka                   (sclk)                          ,
        .ena                    (1'b1)                          ,
        .addra                  (param_rd_addr_layer2) ,
        .douta                  (param_w_h2_layer2)
    );

endmodule
