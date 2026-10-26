//****************************************Copyright (c)***********************************//
//原子哥在线教学平台：www.yuanzige.com
//技术支持：http://www.openedv.com/forum.php
//淘宝店铺：https://zhengdianyuanzi.tmall.com
//关注微信公众平台微信号："正点原子"，免费获取ZYNQ & FPGA & STM32 & LINUX资料。
//版权所有，盗版必究。
//Copyright(C) 正点原子 2023-2033
//All rights reserved                                  
//----------------------------------------------------------------------------------------
// File name:           i2c_reg_cfg
// Created by:          正点原子
// Created date:        2023年2月3日14:17:02
// Version:             V1.0
// Descriptions:        i2c_reg_cfg
//
//----------------------------------------------------------------------------------------
//****************************************************************************************//

// Board microphone variant. Register details are in README.md.
module i2c_reg_cfg #(
    parameter  WL          = 6'd24,         
    parameter  PHONE_VOLUME = 7'd103,        
    parameter  SPEAK_VOLUME = 7'd0         
)(
    input                clk      ,         
    input                rst_n    ,         
    input [1:0]          mic_gain,
    input line_input,
    input                i2c_done ,         

    output  reg          i2c_exec ,         
    output  reg  [15:0]  i2c_data ,         
    output  reg          cfg_done           
);

localparam REG_NUM      = 5'd25;            

reg    [1:0]  wl            ;               
reg    [7:0]  start_init_cnt;               
reg    [4:0]  init_reg_cnt  ;               






always @(posedge clk or negedge rst_n) begin
    if(!rst_n)
        wl <= 2'b00;
    else begin
        case(WL)
            6'd16:  wl <= 2'b00; 
            6'd20:  wl <= 2'b01; 
            6'd24:  wl <= 2'b10; 
            6'd32:  wl <= 2'b11; 
            default: wl <= 2'd0;
        endcase
    end
end


always @(posedge clk or negedge rst_n) begin
    if(!rst_n)
        start_init_cnt <= 8'd0;
    else if(start_init_cnt < 8'hff)
        start_init_cnt <= start_init_cnt + 1'b1;
end


always @(posedge clk or negedge rst_n) begin
    if(!rst_n)
        i2c_exec <= 1'b0;
    else if(init_reg_cnt == 5'd0 & start_init_cnt == 8'hfe)
        i2c_exec <= 1'b1;
    else if(i2c_done && init_reg_cnt < REG_NUM)
        i2c_exec <= 1'b1;
    else
        i2c_exec <= 1'b0;
end


always @(posedge clk or negedge rst_n) begin
    if(!rst_n)
        init_reg_cnt <= 5'd0;
    else if(i2c_exec)
        init_reg_cnt <= init_reg_cnt + 1'b1;
end


always @(posedge clk or negedge rst_n) begin
    if(!rst_n)
        cfg_done <= 1'b0;
    else if(i2c_done & (init_reg_cnt == REG_NUM) )
        cfg_done <= 1'b1;
end


always @(posedge clk or negedge rst_n) begin
    if(!rst_n)
        i2c_data <= 16'b0;
    else begin
        case(init_reg_cnt)

                    
            5'd0 : i2c_data <= {7'd15 ,9'd0};

                    
            5'd1 : i2c_data <= {7'd25 ,(line_input ? 9'h0FC : 9'h0FE)};
                    
            5'd2 : i2c_data <= {7'd26 ,9'h1E1};
                    
            5'd3: i2c_data <=  {7'd47 ,9'h02C};

                    
            5'd4: i2c_data <= {7'd34 ,9'b1_0000_0000};
                    
            5'd5: i2c_data <= {7'd37 ,9'b1_0000_0000};
                    
            5'd6: i2c_data <= {7'd5,9'b0_0000_0000};
                    
            5'd7: i2c_data <= {7'd2 ,{2'b10,PHONE_VOLUME}};
                    
            5'd8: i2c_data <= {7'd3 ,{2'b10,PHONE_VOLUME}};

                    
            5'd9: i2c_data <= {7'd51,9'b0_1001_1011};  
                    
            5'd10: i2c_data <= {7'd49,9'h037};      
                    
            5'd11: i2c_data <= {7'd40,{2'b10,SPEAK_VOLUME}};  
                    
            5'd12: i2c_data <= {7'd41,{2'b10,SPEAK_VOLUME}};             

                    
            5'd13: i2c_data <= {7'd43,(line_input ? 9'h050 : 9'h000)};
                    
            5'd14: i2c_data <= {7'd44,9'h000}; 

                    
            5'd15: i2c_data <= {7'd7,{5'b0_0100,wl,2'b10}};
                    
            5'd16: i2c_data <= {7'd24,9'b0_0000_0100};
                    
            5'd17: i2c_data <= {7'd9,9'b0_0100_0000};           

                    
            5'd18: i2c_data <= {7'd4,9'b0_0000_0101};
                    
            5'd19: i2c_data <= {7'd8,9'b1_1100_0000};
                    
            5'd20: i2c_data <= {7'd52,9'b0_0010_1000};
            5'd21: i2c_data <= {7'd0, (line_input ? 9'h117 : (mic_gain == 0 ? 9'h117 : mic_gain == 2 ? 9'h137 : 9'h127))};
            5'd22: i2c_data <= {7'd1, 9'h197};
            5'd23: i2c_data <= {7'd32,(line_input ? 9'h100 : 9'h158)};
            5'd24: i2c_data <= {7'd33,9'h100};
            default : ;
        endcase 
    end
end

endmodule 