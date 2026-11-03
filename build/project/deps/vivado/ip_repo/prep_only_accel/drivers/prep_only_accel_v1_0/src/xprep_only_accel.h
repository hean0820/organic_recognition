// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2020.2 (64-bit)
// Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
// ==============================================================
#ifndef XPREP_ONLY_ACCEL_H
#define XPREP_ONLY_ACCEL_H

#ifdef __cplusplus
extern "C" {
#endif

/***************************** Include Files *********************************/
#ifndef __linux__
#include "xil_types.h"
#include "xil_assert.h"
#include "xstatus.h"
#include "xil_io.h"
#else
#include <stdint.h>
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#endif
#include "xprep_only_accel_hw.h"

/**************************** Type Definitions ******************************/
#ifdef __linux__
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef struct {
    u16 DeviceId;
    u32 Control_BaseAddress;
} XPrep_only_accel_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XPrep_only_accel;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XPrep_only_accel_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XPrep_only_accel_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XPrep_only_accel_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XPrep_only_accel_ReadReg(BaseAddress, RegOffset) \
    *(volatile u32*)((BaseAddress) + (RegOffset))

#define Xil_AssertVoid(expr)    assert(expr)
#define Xil_AssertNonvoid(expr) assert(expr)

#define XST_SUCCESS             0
#define XST_DEVICE_NOT_FOUND    2
#define XST_OPEN_DEVICE_FAILED  3
#define XIL_COMPONENT_IS_READY  1
#endif

/************************** Function Prototypes *****************************/
#ifndef __linux__
int XPrep_only_accel_Initialize(XPrep_only_accel *InstancePtr, u16 DeviceId);
XPrep_only_accel_Config* XPrep_only_accel_LookupConfig(u16 DeviceId);
int XPrep_only_accel_CfgInitialize(XPrep_only_accel *InstancePtr, XPrep_only_accel_Config *ConfigPtr);
#else
int XPrep_only_accel_Initialize(XPrep_only_accel *InstancePtr, const char* InstanceName);
int XPrep_only_accel_Release(XPrep_only_accel *InstancePtr);
#endif

void XPrep_only_accel_Start(XPrep_only_accel *InstancePtr);
u32 XPrep_only_accel_IsDone(XPrep_only_accel *InstancePtr);
u32 XPrep_only_accel_IsIdle(XPrep_only_accel *InstancePtr);
u32 XPrep_only_accel_IsReady(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_EnableAutoRestart(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_DisableAutoRestart(XPrep_only_accel *InstancePtr);
u32 XPrep_only_accel_Get_return(XPrep_only_accel *InstancePtr);

void XPrep_only_accel_Set_frame(XPrep_only_accel *InstancePtr, u64 Data);
u64 XPrep_only_accel_Get_frame(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_Set_detection(XPrep_only_accel *InstancePtr, u64 Data);
u64 XPrep_only_accel_Get_detection(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_Set_gray(XPrep_only_accel *InstancePtr, u64 Data);
u64 XPrep_only_accel_Get_gray(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_Set_horizontal(XPrep_only_accel *InstancePtr, u64 Data);
u64 XPrep_only_accel_Get_horizontal(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_Set_ink(XPrep_only_accel *InstancePtr, u64 Data);
u64 XPrep_only_accel_Get_ink(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_Set_stride_words(XPrep_only_accel *InstancePtr, u32 Data);
u32 XPrep_only_accel_Get_stride_words(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_Set_mode(XPrep_only_accel *InstancePtr, u32 Data);
u32 XPrep_only_accel_Get_mode(XPrep_only_accel *InstancePtr);

void XPrep_only_accel_InterruptGlobalEnable(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_InterruptGlobalDisable(XPrep_only_accel *InstancePtr);
void XPrep_only_accel_InterruptEnable(XPrep_only_accel *InstancePtr, u32 Mask);
void XPrep_only_accel_InterruptDisable(XPrep_only_accel *InstancePtr, u32 Mask);
void XPrep_only_accel_InterruptClear(XPrep_only_accel *InstancePtr, u32 Mask);
u32 XPrep_only_accel_InterruptGetEnabled(XPrep_only_accel *InstancePtr);
u32 XPrep_only_accel_InterruptGetStatus(XPrep_only_accel *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
