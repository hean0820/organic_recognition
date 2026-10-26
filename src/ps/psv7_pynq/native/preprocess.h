#ifndef PREPROCESS_H
#define PREPROCESS_H
#include <stddef.h>
#include <stdint.h>
#include "phase1_config.h"

/* v1: source ROI is shared with PL display; BGR bytes in little-endian DDR. */
#define PREP_VERSION 0x00010000U
#define PREP_DETECT_W 640U
#define PREP_DETECT_H 267U
#define PREP_TRIM_X0 51U
#define PREP_TRIM_Y0 21U
#define PREP_WORK_W 537U
#define PREP_WORK_H 224U
#define PREP_DETECT_N (PREP_DETECT_W*PREP_DETECT_H)
#define PREP_WORK_N (PREP_WORK_W*PREP_WORK_H)
#define PREP_INPUT_N 4096U

typedef enum {
    PREP_OK=0, PREP_BLANK, PREP_EDGE, PREP_DARK, PREP_WEAK, PREP_BAD_ARGUMENT, PREP_ACCEL_ERROR
} PrepCode;
typedef struct {
    uint32_t version, code, threshold, components, kept, foreground_pixels;
    uint32_t bbox_x, bbox_y, bbox_w, bbox_h, crop_x, crop_y, crop_w, crop_h;
    uint32_t high_milli, resized_w, resized_h, mean_gray;
    uint32_t detect_crc, input_crc, stage_us[6], total_us;
} PrepReport;
typedef struct {
    uint8_t detection[PREP_DETECT_N], gray[PREP_WORK_N], ink[PREP_WORK_N];
    uint8_t visited[PREP_WORK_N], crop[PREP_WORK_N];
    uint32_t queue[PREP_WORK_N];
} PrepWorkspace;
typedef struct {void *context; uint32_t (*now_us)(void *context);} PrepClock;
typedef struct {
    void *context;
    PrepCode (*run)(void *context,const uint8_t *frame,size_t bytes,size_t stride,
                   PrepWorkspace *work,uint8_t *output,PrepReport *report,const PrepClock *clock);
} PrepBackend;

uint32_t prep_crc32(const uint8_t *data, size_t bytes);
const char *prep_code_name(PrepCode code);
/* gray/ink/detection have been produced by PL, then retain exact PS postprocessing. */
PrepCode prep_from_filtered(PrepWorkspace *work,uint8_t output[PREP_INPUT_N],
                            PrepReport *report,const PrepClock *clock);
#endif
