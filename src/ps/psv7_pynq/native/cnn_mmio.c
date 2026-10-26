/* Use the existing PYNQ Device mapping. Only aligned volatile 32-bit accesses;
 * never memcpy/vectorize an MMIO window or touch command/status registers. */
#include "cnn_mmio.h"
#include <stddef.h>
static int mapping_ok(const volatile uint32_t *registers,uint32_t bytes)
{
    return registers && !((uintptr_t)registers&3U) && bytes>=0x10000U;
}
static uint32_t packed(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1]<<8) |
           ((uint32_t)bytes[2]<<16) | ((uint32_t)bytes[3]<<24);
}
int psv7_cnn_write_input(volatile uint32_t *registers,uint32_t map_bytes,
                         const uint8_t *input,uint32_t input_bytes)
{
    uint32_t i;
    if(!mapping_ok(registers,map_bytes) || !input || input_bytes!=4096U) return -1;
    __sync_synchronize();
    for(i=0;i<1024U;++i) registers[0x1000U/4U+i]=packed(input+4U*i);
    __sync_synchronize();
    return 0;
}
int psv7_cnn_verify_input(const volatile uint32_t *registers,uint32_t map_bytes,
                         const uint8_t *input,uint32_t input_bytes,uint32_t *mismatch)
{
    uint32_t i;
    if(!mapping_ok(registers,map_bytes) || !input || input_bytes!=4096U || !mismatch) return -1;
    *mismatch=UINT32_MAX;__sync_synchronize();
    for(i=0;i<1024U;++i) {
        if(registers[0x1000U/4U+i]!=packed(input+4U*i)) {*mismatch=i;return -2;}
    }
    __sync_synchronize();
    return 0;
}
int psv7_cnn_read_logits(const volatile uint32_t *registers,uint32_t map_bytes,
                        int32_t *logits,uint32_t logit_count)
{
    uint32_t i;
    if(!mapping_ok(registers,map_bytes) || !logits || logit_count!=22U) return -1;
    __sync_synchronize();
    for(i=0;i<22U;++i) logits[i]=(int32_t)registers[0x4000U/4U+i];
    __sync_synchronize();
    return 0;
}
