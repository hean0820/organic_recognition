// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2020.2 (64-bit)
// Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
// ==============================================================
#ifndef __linux__

#include "xstatus.h"
#include "xparameters.h"
#include "xprep_accel.h"

extern XPrep_accel_Config XPrep_accel_ConfigTable[];

XPrep_accel_Config *XPrep_accel_LookupConfig(u16 DeviceId) {
	XPrep_accel_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XPREP_ACCEL_NUM_INSTANCES; Index++) {
		if (XPrep_accel_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XPrep_accel_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XPrep_accel_Initialize(XPrep_accel *InstancePtr, u16 DeviceId) {
	XPrep_accel_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XPrep_accel_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XPrep_accel_CfgInitialize(InstancePtr, ConfigPtr);
}

#endif

