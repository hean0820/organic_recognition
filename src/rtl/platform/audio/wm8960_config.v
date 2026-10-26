//****************************************Copyright (c)***********************************//
//原子哥在线教学平台：www.yuanzige.com
//技术支持：http://www.openedv.com/forum.php
//淘宝店铺：https://zhengdianyuanzi.tmall.com
//关注微信公众平台微信号："正点原子"，免费获取ZYNQ & FPGA & STM32 & LINUX资料。
//版权所有，盗版必究。
//Copyright(C) 正点原子 2023-2033
//All rights reserved                                  
//----------------------------------------------------------------------------------------
// File name:           wm8960_config
// Created by:          正点原子
// Created date:        2023年2月3日14:17:02
// Version:             V1.0
// Descriptions:        wm8960_config
//
//----------------------------------------------------------------------------------------
//****************************************************************************************/

module wm8960_config #(
    parameter   SLAVE_ADDR = 7'h1A         ,    // 器件地址1A
    parameter   WL         = 6'd24         ,    // word length音频字长参数设置
    parameter   BIT_CTRL   = 1'b0          ,    // 地址位宽控制(1:16b; 0:8b)
    parameter   CLK_FREQ   = 26'd50_000_000,    // i2c_dri模块的驱动时钟频率(CLK_FREQ)
    parameter   I2C_FREQ   = 18'd250_000        // I2C的SCL时钟频率
)(
    input       clk     ,                   // 时钟信号
    input [1:0] mic_gain,
    input line_input,
    output      cfg_done,
    output reg  nack_seen,
    input       rst_n   ,                   // 复位信号
                                            
    output      aud_scl ,                   // WM8960的SCL时钟
    inout       aud_sda                     // WM8960的SDA信号
);
//wire define
wire        clk_i2c   ;                     // i2c的操作时钟
wire        i2c_exec  ;                     // i2c触发控制
wire        i2c_done  ;                     // i2c操作结束标志
// cfg_done is an output.                      // WM8978配置完成标志
wire [15:0] reg_data  ;                     // WM8978需要配置的寄存器（地址及数据）
wire        i2c_ack   ;

//*****************************************************
//**                    main code
//*****************************************************

//配置WM8960的寄存器
i2c_reg_cfg #(
    .WL             (WL       )             // word length音频字长参数设置
) u_i2c_reg_cfg(  
    .clk            (clk_i2c  ),            // i2c_reg_cfg驱动时钟
    .rst_n          (rst_n    ),            // 复位信号
    .mic_gain       (mic_gain ),
    .line_input     (line_input),
    .i2c_done       (i2c_done ),            // I2C一次操作完成的标志信号  
    
    .i2c_exec       (i2c_exec ),            // I2C触发执行信号
    .i2c_data       (reg_data ),            // 寄存器数据（7位地址+9位数据）
    .cfg_done       (cfg_done )             // WM8960配置完成    
);

//调用IIC协议
i2c_dri #(
    .SLAVE_ADDR     (SLAVE_ADDR),           // slave address从机地址
    .CLK_FREQ       (CLK_FREQ  ),           // i2c_dri模块的驱动时钟频率(CLK_FREQ)
    .I2C_FREQ       (I2C_FREQ  )            // I2C的SCL时钟频率
) u_i2c_dri(  
    .clk            (clk       ),           // i2c_dri模块的驱动时钟(CLK_FREQ)
    .rst_n          (rst_n     ),           // 复位信号
    .i2c_exec       (i2c_exec  ),           // I2C触发执行信号
    .bit_ctrl       (BIT_CTRL  ),           // 器件地址位控制(16b/8b)
    .i2c_rh_wl      (1'b0      ),           // I2C读写控制信号
    .i2c_addr       (reg_data[15:8]),       // I2C器件字地址
    .i2c_data_w     (reg_data[ 7:0]),       // I2C要写的数据
    
    .i2c_data_r     (),                     // I2C读出的数据
    .i2c_done       (i2c_done  ),           // I2C一次操作完成
    .i2c_ack        (i2c_ack),
    .scl            (aud_scl   ),           // I2C的SCL时钟信号
    .sda            (aud_sda   ),           // I2C的SDA信号
    .dri_clk        (clk_i2c   )            // I2C操作时钟
);

always @(posedge clk_i2c or negedge rst_n) begin
    if (!rst_n) nack_seen <= 0;
    else if (i2c_done && i2c_ack) nack_seen <= 1;
end

endmodule 