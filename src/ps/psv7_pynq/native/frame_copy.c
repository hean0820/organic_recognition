/* Normal CPU memory only. Source VDMA slot must already be parked/invalidate'd.
 * Copy four packed BGR pixels while checking their RGB565-expanded low bits.
 * memcpy of constant 4-byte sizes avoids aliasing/unaligned C pointer casts. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>

uint32_t psv7_copy_validate_rgb565(const uint8_t *source,uint8_t *destination,uint32_t pixels)
{
    uint32_t i,bad=0;uintptr_t src=(uintptr_t)source,dst=(uintptr_t)destination;
    const uintptr_t bytes=720U*1280U*3U;
    if(!source || !destination || pixels!=720U*1280U ||
       (src<dst ? dst-src<bytes : src-dst<bytes)) return UINT32_MAX;
    for(i=0;i<pixels;i+=4U,source+=12,destination+=12) {
        uint32_t a,b,c;
        memcpy(&a,source,4);memcpy(&b,source+4,4);memcpy(&c,source+8,4);
        memcpy(destination,&a,4);memcpy(destination+4,&b,4);memcpy(destination+8,&c,4);
        bad+=(a&UINT32_C(0x00070307))!=0U;
        bad+=((a>>24)&7U || (b&UINT32_C(0x00000703)))!=0U;
        bad+=((b>>16)&UINT32_C(0x00000307) || (c&7U))!=0U;
        bad+=((c>>8)&UINT32_C(0x00070307))!=0U;
    }
    return bad;
}
