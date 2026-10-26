//****************************************Copyright (c)***********************************//
//原子哥在线教学平台：www.yuanzige.com
//技术支持：http://www.openedv.com/forum.php
//淘宝店铺：https://zhengdianyuanzi.tmall.com
//关注微信公众平台微信号："正点原子"，免费获取ZYNQ & FPGA & STM32 & LINUX资料。
//版权所有，盗版必究。
//Copyright(C) 正点原子 2023-2033
//All rights reserved                                  
//----------------------------------------------------------------------------------------
// File name:           audio_receive
// Created by:          正点原子
// Created date:        2023年2月3日14:17:02
// Version:             V1.0
// Descriptions:        audio_receive
//
//----------------------------------------------------------------------------------------
//****************************************************************************************//

module audio_receive #(
    parameter WL = 6'd24                 // WL(word length音频字长定义)
) (      
    input                 rst_n     ,     // 复位信号
    input                 aud_bclk  ,     // WM8960位时钟
    input                 aud_lrc   ,     // 左右通道时钟
    input                 aud_adcdat,     // 音频输入
    
    output  reg           rx_done   ,     // FPGA接收数据完成
    output  reg [WL-1:0]  adc_data        // FPGA接收的数据
    
);
//reg define
reg              aud_lrc_d0;              // aud_lrc延迟一个时钟周期
reg    [ 5:0]    rx_cnt;                  // 发送数据计数
reg    [WL-1:0]  adc_data_t;              // 预输出的音频数据的暂存值
//wire define
wire             lrc_edge ;               // 边沿信号

//*****************************************************
//**                    main code
//*****************************************************

assign   lrc_edge = aud_lrc ^ aud_lrc_d0; // LRC信号的边沿检测

//为了在aud_lrc变化的第二个AUD_BCLK上升沿采集aud_adcdat,延迟打拍采集
always @(posedge aud_bclk or negedge rst_n) begin
    if(!rst_n)
        aud_lrc_d0 <= 1'b0;
    else
        aud_lrc_d0 <= aud_lrc;
end

//采集24位音频数据的计数
always @(posedge aud_bclk or negedge rst_n) begin
    if(!rst_n)
        rx_cnt <= 6'd0;
    else if(lrc_edge == 1'b1)
        rx_cnt <= 6'd0;
    else if(rx_cnt <= WL)
        rx_cnt <= rx_cnt + 1'b1;
end

//把采集到的音频数据临时存放在一个寄存器内
always @(posedge aud_bclk or negedge rst_n) begin
    if(!rst_n)
        adc_data_t <= 0;
    else if(rx_cnt < WL)
        adc_data_t[WL - 1'd1 - rx_cnt] <= aud_adcdat;
end

//把临时数据传递给adc_data,并使能rx_done,表明一次采集完成
always @(posedge aud_bclk or negedge rst_n) begin
    if(!rst_n) begin
        rx_done   <=  1'b0;
        adc_data  <=  0;
    end
    else if(rx_cnt == WL) begin
        rx_done <= 1'b1;
        adc_data<= adc_data_t;
    end
    else
        rx_done <= 1'b0;
end

endmodule 