// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2020.2 (64-bit)
// Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
// ==============================================================
// control
// 0x00 : Control signals
//        bit 0  - ap_start (Read/Write/COH)
//        bit 1  - ap_done (Read/COR)
//        bit 2  - ap_idle (Read)
//        bit 3  - ap_ready (Read)
//        bit 7  - auto_restart (Read/Write)
//        others - reserved
// 0x04 : Global Interrupt Enable Register
//        bit 0  - Global Interrupt Enable (Read/Write)
//        others - reserved
// 0x08 : IP Interrupt Enable Register (Read/Write)
//        bit 0  - enable ap_done interrupt (Read/Write)
//        bit 1  - enable ap_ready interrupt (Read/Write)
//        others - reserved
// 0x0c : IP Interrupt Status Register (Read/TOW)
//        bit 0  - ap_done (COR/TOW)
//        bit 1  - ap_ready (COR/TOW)
//        others - reserved
// 0x10 : Data signal of ap_return
//        bit 31~0 - ap_return[31:0] (Read)
// 0x18 : Data signal of frame
//        bit 31~0 - frame[31:0] (Read/Write)
// 0x1c : Data signal of frame
//        bit 31~0 - frame[63:32] (Read/Write)
// 0x20 : reserved
// 0x24 : Data signal of detection
//        bit 31~0 - detection[31:0] (Read/Write)
// 0x28 : Data signal of detection
//        bit 31~0 - detection[63:32] (Read/Write)
// 0x2c : reserved
// 0x30 : Data signal of gray
//        bit 31~0 - gray[31:0] (Read/Write)
// 0x34 : Data signal of gray
//        bit 31~0 - gray[63:32] (Read/Write)
// 0x38 : reserved
// 0x3c : Data signal of horizontal
//        bit 31~0 - horizontal[31:0] (Read/Write)
// 0x40 : Data signal of horizontal
//        bit 31~0 - horizontal[63:32] (Read/Write)
// 0x44 : reserved
// 0x48 : Data signal of ink
//        bit 31~0 - ink[31:0] (Read/Write)
// 0x4c : Data signal of ink
//        bit 31~0 - ink[63:32] (Read/Write)
// 0x50 : reserved
// 0x54 : Data signal of stride_words
//        bit 31~0 - stride_words[31:0] (Read/Write)
// 0x58 : reserved
// 0x5c : Data signal of mode
//        bit 31~0 - mode[31:0] (Read/Write)
// 0x60 : reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XPREP_ACCEL_CONTROL_ADDR_AP_CTRL           0x00
#define XPREP_ACCEL_CONTROL_ADDR_GIE               0x04
#define XPREP_ACCEL_CONTROL_ADDR_IER               0x08
#define XPREP_ACCEL_CONTROL_ADDR_ISR               0x0c
#define XPREP_ACCEL_CONTROL_ADDR_AP_RETURN         0x10
#define XPREP_ACCEL_CONTROL_BITS_AP_RETURN         32
#define XPREP_ACCEL_CONTROL_ADDR_FRAME_DATA        0x18
#define XPREP_ACCEL_CONTROL_BITS_FRAME_DATA        64
#define XPREP_ACCEL_CONTROL_ADDR_DETECTION_DATA    0x24
#define XPREP_ACCEL_CONTROL_BITS_DETECTION_DATA    64
#define XPREP_ACCEL_CONTROL_ADDR_GRAY_DATA         0x30
#define XPREP_ACCEL_CONTROL_BITS_GRAY_DATA         64
#define XPREP_ACCEL_CONTROL_ADDR_HORIZONTAL_DATA   0x3c
#define XPREP_ACCEL_CONTROL_BITS_HORIZONTAL_DATA   64
#define XPREP_ACCEL_CONTROL_ADDR_INK_DATA          0x48
#define XPREP_ACCEL_CONTROL_BITS_INK_DATA          64
#define XPREP_ACCEL_CONTROL_ADDR_STRIDE_WORDS_DATA 0x54
#define XPREP_ACCEL_CONTROL_BITS_STRIDE_WORDS_DATA 32
#define XPREP_ACCEL_CONTROL_ADDR_MODE_DATA         0x5c
#define XPREP_ACCEL_CONTROL_BITS_MODE_DATA         32

