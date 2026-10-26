// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2020.2 (64-bit)
// Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
// ==============================================================
/***************************** Include Files *********************************/
#include "xprep_accel.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XPrep_accel_CfgInitialize(XPrep_accel *InstancePtr, XPrep_accel_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XPrep_accel_Start(XPrep_accel *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_CTRL) & 0x80;
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XPrep_accel_IsDone(XPrep_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XPrep_accel_IsIdle(XPrep_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XPrep_accel_IsReady(XPrep_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XPrep_accel_EnableAutoRestart(XPrep_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XPrep_accel_DisableAutoRestart(XPrep_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_CTRL, 0);
}

u32 XPrep_accel_Get_return(XPrep_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_AP_RETURN);
    return Data;
}
void XPrep_accel_Set_frame(XPrep_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_FRAME_DATA, (u32)(Data));
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_FRAME_DATA + 4, (u32)(Data >> 32));
}

u64 XPrep_accel_Get_frame(XPrep_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_FRAME_DATA);
    Data += (u64)XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_FRAME_DATA + 4) << 32;
    return Data;
}

void XPrep_accel_Set_detection(XPrep_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_DETECTION_DATA, (u32)(Data));
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_DETECTION_DATA + 4, (u32)(Data >> 32));
}

u64 XPrep_accel_Get_detection(XPrep_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_DETECTION_DATA);
    Data += (u64)XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_DETECTION_DATA + 4) << 32;
    return Data;
}

void XPrep_accel_Set_gray(XPrep_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_GRAY_DATA, (u32)(Data));
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_GRAY_DATA + 4, (u32)(Data >> 32));
}

u64 XPrep_accel_Get_gray(XPrep_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_GRAY_DATA);
    Data += (u64)XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_GRAY_DATA + 4) << 32;
    return Data;
}

void XPrep_accel_Set_horizontal(XPrep_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_HORIZONTAL_DATA, (u32)(Data));
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_HORIZONTAL_DATA + 4, (u32)(Data >> 32));
}

u64 XPrep_accel_Get_horizontal(XPrep_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_HORIZONTAL_DATA);
    Data += (u64)XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_HORIZONTAL_DATA + 4) << 32;
    return Data;
}

void XPrep_accel_Set_ink(XPrep_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_INK_DATA, (u32)(Data));
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_INK_DATA + 4, (u32)(Data >> 32));
}

u64 XPrep_accel_Get_ink(XPrep_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_INK_DATA);
    Data += (u64)XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_INK_DATA + 4) << 32;
    return Data;
}

void XPrep_accel_Set_stride_words(XPrep_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_STRIDE_WORDS_DATA, Data);
}

u32 XPrep_accel_Get_stride_words(XPrep_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_STRIDE_WORDS_DATA);
    return Data;
}

void XPrep_accel_Set_mode(XPrep_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_MODE_DATA, Data);
}

u32 XPrep_accel_Get_mode(XPrep_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_MODE_DATA);
    return Data;
}

void XPrep_accel_InterruptGlobalEnable(XPrep_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_GIE, 1);
}

void XPrep_accel_InterruptGlobalDisable(XPrep_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_GIE, 0);
}

void XPrep_accel_InterruptEnable(XPrep_accel *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_IER);
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_IER, Register | Mask);
}

void XPrep_accel_InterruptDisable(XPrep_accel *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_IER);
    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_IER, Register & (~Mask));
}

void XPrep_accel_InterruptClear(XPrep_accel *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPrep_accel_WriteReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_ISR, Mask);
}

u32 XPrep_accel_InterruptGetEnabled(XPrep_accel *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_IER);
}

u32 XPrep_accel_InterruptGetStatus(XPrep_accel *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XPrep_accel_ReadReg(InstancePtr->Control_BaseAddress, XPREP_ACCEL_CONTROL_ADDR_ISR);
}

