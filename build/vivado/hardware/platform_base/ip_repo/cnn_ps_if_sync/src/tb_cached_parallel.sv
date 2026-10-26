`timescale 1ns/1ps

// 全部六个阶段逐值对拍；第二帧不复位，验证缓存/部分和不会混入上一帧。
module tb_cached_parallel;

    parameter integer LANES = 2;
    parameter integer FRAMES = 3;

    reg                     clk = 0;
    reg                     rst_n = 0;
    reg                     image_valid = 0;
    reg         [7:0]       image_data = 0;

    wire                    image_ready;
    wire                    frame_done;
    wire        [7:0]       pool_data;
    wire                    pool_valid;

    reg         [7:0]       image [0:4095];
    reg         [31:0]      c1_acc [0:98303];
    reg         [31:0]      c2_acc [0:49151];
    reg         [7:0]       c1_act [0:98303];
    reg         [7:0]       p1 [0:24575];
    reg         [7:0]       c2_act [0:49151];
    reg         [7:0]       p2 [0:12287];

    integer                 frame, pixel, lane, index;
    integer                 c1_count, a1_count, p1_count, p2_count;
    integer                 c2_count [0:LANES-1];
    integer                 a2_count [0:LANES-1];
    integer                 lane_pool_count [0:LANES-1];
    integer                 starts, groups, ic_completions, done_count;
    integer                 frame_cycles, seed = 216020;
    reg                     checking = 0;
    // 交付包专用：数据和验收文件路径由 Tcl plusargs 提供。
    // 原来的五个 RTL 文件保持逐字节不变。
    reg         [4095:0]    path;
    reg         [4095:0]    data_root = "data";
    reg         [4095:0]    result_path = "simulation_result.txt";
    integer                 result_fd, plusarg_found;

    always #5 clk = ~clk;

    cnn_top #(
        .CONV2_LANES            (LANES)
    ) dut (
        .sclk                   (clk),
        .s_rst_n                (rst_n),
        .image_data             (image_data),
        .image_data_vld         (image_valid),
        .image_data_ready       (image_ready),
        .pool_data_out          (pool_data),
        .pool_data_out_vld      (pool_valid),
        .frame_done             (frame_done)
    );

    task load_case;
        input integer id;
        begin
            $sformat(path, "%0s/case%0d_input.mem", data_root, id);
            $readmemh(path, image);
            $sformat(path, "%0s/case%0d_conv1_acc.mem", data_root, id);
            $readmemh(path, c1_acc);
            $sformat(path, "%0s/case%0d_conv1_act.mem", data_root, id);
            $readmemh(path, c1_act);
            $sformat(path, "%0s/case%0d_pool1.mem", data_root, id);
            $readmemh(path, p1);
            $sformat(path, "%0s/case%0d_conv2_acc.mem", data_root, id);
            $readmemh(path, c2_acc);
            $sformat(path, "%0s/case%0d_conv2_act.mem", data_root, id);
            $readmemh(path, c2_act);
            $sformat(path, "%0s/case%0d_pool2.mem", data_root, id);
            $readmemh(path, p2);
        end
    endtask

    always @(posedge clk) begin
        if (rst_n && checking) begin
            if (dut.cache_rd_en && !dut.cache_frame_ready)
                $fatal(1, "Pool1 cache read before full frame committed");
            if (dut.pool_data_vld_layer1 && dut.cache_rd_en)
                $fatal(1, "Pool1 cache is read and overwritten simultaneously");

            #1;
            frame_cycles = frame_cycles + 1;

            if (dut.cal_start_layer1) starts = starts + 1;
            if (dut.conv2_channel_done) ic_completions = ic_completions + 1;

            if (dut.conv2_group_start) begin
                groups = groups + 1;
                for (lane = 0; lane < LANES; lane = lane + 1) begin
                    c2_count[lane] = 0;
                    a2_count[lane] = 0;
                    lane_pool_count[lane] = 0;
                end
            end

            if (dut.conv_rslt_out_valid_layer1) begin
                if (c1_count >= 98304 || dut.conv_rslt_out_layer1 !== c1_acc[c1_count])
                    $fatal(1, "Conv1 mismatch frame=%0d index=%0d got=%0d expected=%0d",
                        frame, c1_count, $signed(dut.conv_rslt_out_layer1), $signed(c1_acc[c1_count]));
                c1_count = c1_count + 1;
            end

            if (dut.conv_rslt_act_valid_layer1) begin
                if (a1_count >= 98304 || dut.conv_rslt_act_layer1 !== c1_act[a1_count])
                    $fatal(1, "Conv1 ReLU mismatch index=%0d", a1_count);
                a1_count = a1_count + 1;
            end

            if (dut.pool_data_vld_layer1) begin
                if (p1_count >= 24576 || dut.pool_data_layer1 !== p1[p1_count])
                    $fatal(1, "Pool1 mismatch index=%0d got=%0d expected=%0d", p1_count, dut.pool_data_layer1, p1[p1_count]);
                p1_count = p1_count + 1;
            end

            for (lane = 0; lane < LANES; lane = lane + 1) begin
                if (dut.conv2_rslt_valid[lane]) begin
                    index = (dut.conv2_active_group_oc + lane) * 1024 + c2_count[lane];
                    if (c2_count[lane] >= 1024 || dut.conv2_rslt_bus[lane*32 +: 32] !== c2_acc[index])
                        $fatal(1, "Conv2 mismatch frame=%0d OC=%0d index=%0d got=%0d expected=%0d IC=%0d",
                            frame, dut.conv2_active_group_oc + lane, c2_count[lane],
                            $signed(dut.conv2_rslt_bus[lane*32 +: 32]), $signed(c2_acc[index]), dut.conv2_in_cnt);
                    c2_count[lane] = c2_count[lane] + 1;
                end

                if (dut.conv2_act_valid[lane]) begin
                    index = (dut.conv2_active_group_oc + lane) * 1024 + a2_count[lane];
                    if (a2_count[lane] >= 1024 || dut.conv2_act_bus[lane*8 +: 8] !== c2_act[index])
                        $fatal(1, "Conv2 ReLU mismatch OC=%0d index=%0d", dut.conv2_active_group_oc + lane, a2_count[lane]);
                    a2_count[lane] = a2_count[lane] + 1;
                end

                if (dut.pool2_lane_valid[lane]) begin
                    index = (dut.conv2_active_group_oc + lane) * 256 + lane_pool_count[lane];
                    if (lane_pool_count[lane] >= 256 || dut.pool2_lane_data[lane*8 +: 8] !== p2[index])
                        $fatal(1, "Pool2 lane mismatch OC=%0d index=%0d", dut.conv2_active_group_oc + lane, lane_pool_count[lane]);
                    lane_pool_count[lane] = lane_pool_count[lane] + 1;
                end
            end

            if (pool_valid) begin
                if (p2_count >= 12288 || pool_data !== p2[p2_count])
                    $fatal(1, "CHW output mismatch index=%0d got=%0d expected=%0d", p2_count, pool_data, p2[p2_count]);
                p2_count = p2_count + 1;
            end

            if (dut.output_group_done) begin
                for (lane = 0; lane < LANES; lane = lane + 1) begin
                    if (c2_count[lane] != 1024 || a2_count[lane] != 1024 || lane_pool_count[lane] != 256)
                        $fatal(1, "Incomplete output group OC=%0d lane=%0d", dut.conv2_active_group_oc, lane);
                end
                if (dut.conv2_active_group_oc % 8 == 0) begin
                    $display("PROGRESS LANES=%0d frame=%0d OC=%0d cycle=%0d", LANES, frame, dut.conv2_active_group_oc, frame_cycles);
                    $fflush();
                end
            end

            if (frame_done) begin
                done_count = done_count + 1;
                if (!pool_valid || p2_count != 12288) $fatal(1, "Frame done did not align with last Pool2 sample");
            end
        end
    end

    initial begin
        plusarg_found = $value$plusargs("DATA_DIR=%s", data_root);
        plusarg_found = $value$plusargs("RESULT_FILE=%s", result_path);
        result_fd = $fopen(result_path, "w");
        if (result_fd == 0) $fatal(1, "Cannot create simulation result file");
        $fdisplay(result_fd, "START frames=%0d lanes=%0d", FRAMES, LANES);
        $fclose(result_fd);

        repeat (4) @(negedge clk);
        rst_n = 1;

        for (frame = 0; frame < FRAMES; frame = frame + 1) begin
            load_case(frame % 3);
            c1_count = 0; a1_count = 0; p1_count = 0; p2_count = 0;
            starts = 0; groups = 0; ic_completions = 0; done_count = 0; frame_cycles = 0;
            checking = 1;

            for (pixel = 0; pixel < 4096; pixel = pixel + 1) begin
                @(negedge clk);
                while (!image_ready) @(negedge clk);
                if (($random(seed) & 7) == 0) begin
                    image_valid = 0;
                    image_data = 8'hff;
                    repeat (2) @(negedge clk);
                end
                image_valid = 1;
                image_data = image[pixel];
            end

            @(negedge clk);
            image_valid = 0;
            image_data = 8'hff;
            wait (done_count == 1);
            repeat (15) @(negedge clk);

            if (c1_count != 98304 || a1_count != 98304 || p1_count != 24576 || p2_count != 12288
                || starts != 24 || groups != 48/LANES || ic_completions != 24*48/LANES || done_count != 1)
                $fatal(1, "Frame count mismatch C1=%0d A1=%0d P1=%0d P2=%0d starts=%0d groups=%0d ICs=%0d done=%0d",
                    c1_count,a1_count,p1_count,p2_count,starts,groups,ic_completions,done_count);

            if (!image_ready || dut.cache_frame_ready || dut.conv2_busy)
                $fatal(1, "Frame resources were not released");

            $display("PASS cached parallel LANES=%0d frame=%0d all six stages and CHW order; cycles=%0d latency_ms=%0.5f",
                LANES,frame,frame_cycles,frame_cycles/100000.0);
            $fflush();
            result_fd = $fopen(result_path, "a");
            $fdisplay(result_fd, "PASS frame=%0d lanes=%0d six stages CHW cycles=%0d", frame, LANES, frame_cycles);
            $fclose(result_fd);
            checking = 0;
        end

        result_fd = $fopen(result_path, "a");
        $fdisplay(result_fd, "ALL_PASS frames=%0d lanes=%0d", FRAMES, LANES);
        $fclose(result_fd);
        $finish;
    end

    initial begin
        #50000000;
        $fatal(1, "Global timeout");
    end

endmodule
