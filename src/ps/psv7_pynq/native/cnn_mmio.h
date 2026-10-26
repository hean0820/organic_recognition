#ifndef PSV7_CNN_MMIO_H
#define PSV7_CNN_MMIO_H
#include <stdint.h>
int psv7_cnn_write_input(volatile uint32_t *,uint32_t,const uint8_t *,uint32_t);
int psv7_cnn_verify_input(const volatile uint32_t *,uint32_t,const uint8_t *,uint32_t,uint32_t *);
int psv7_cnn_read_logits(const volatile uint32_t *,uint32_t,int32_t *,uint32_t);
#endif
