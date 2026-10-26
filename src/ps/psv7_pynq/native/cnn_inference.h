#ifndef CNN_INFERENCE_H
#define CNN_INFERENCE_H
#include "cnn_driver.h"
#include "cnn_fc.h"
/* Existing UI storage is retained. Execution belongs to unified_cnn.py. */
typedef struct {
    CnnTransfer transfer;
    CnnResult result;
    int status, recovery_status, valid;
    unsigned failure_stage;
    uint32_t input_crc, feature_crc, fc_us, total_us;
} CnnInference;
#endif
