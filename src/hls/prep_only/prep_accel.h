#ifndef PREP_ACCEL_H
#define PREP_ACCEL_H
#include <stdint.h>
/* Packed little-endian words. Rows use padded strides: gray/ink 540 bytes,
   horizontal 538 uint16 values. Detection is tightly packed 640x267. */
#define PA_DW 640
#define PA_DH 267
#define PA_W 537
#define PA_H 224
#define PA_ROW_BYTES 540
#define PA_HROW_VALUES 538
#ifdef __cplusplus
extern "C" {
#endif
uint32_t prep_only_accel(const uint32_t *frame,uint32_t *detection,
                    uint32_t *gray,uint32_t *horizontal,uint32_t *ink,
                    uint32_t stride_words,uint32_t mode);
#ifdef __cplusplus
}
#endif
#endif
