#ifndef CNN_DRIVER_H
#define CNN_DRIVER_H
#include <stdint.h>
#define CNN_ID_VERSION UINT32_C(0x4352544C)
#define CNN_ABI_VERSION UINT32_C(0x00010000)
#define CNN_INPUT_OFFSET 0x1000U
#define CNN_LOGITS_OFFSET 0x4000U
#define CNN_LOGIT_COUNT 22U
/* Display/report storage only. No legacy transfer entry points are exported. */
typedef struct {
    uint32_t sequence, cycles, input_count, output_count, error;
    uint32_t write_verify_ms, wait_ms, read_ms;
} CnnTransfer;
typedef struct CnnIo CnnIo;
/* Control and model ownership: drivers/unified_cnn.py. Bulk IO: cnn_mmio.h.
 * The old Pool2 transfer / PS-FC CnnIo API has been retired. */
#endif
