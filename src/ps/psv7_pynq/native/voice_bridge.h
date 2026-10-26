#ifndef PYNQ_VOICE_BRIDGE_H
#define PYNQ_VOICE_BRIDGE_H
#include "app_control.h"
typedef struct {AppControl app;char reason[96];uint32_t revision;} PynqRequest;
#endif
