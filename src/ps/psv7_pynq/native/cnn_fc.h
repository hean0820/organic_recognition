#ifndef CNN_FC_H
#define CNN_FC_H
#include <stdint.h>
#define CNN_INPUT_BYTES 4096U
#define CNN_FEATURE_BYTES 12288U
#define CNN_HIDDEN_COUNT 48U
#define CNN_CLASS_COUNT 22U
typedef struct {
    const int8_t *weight1;
    const int32_t *bias1;
    const int8_t *weight2;
    const int32_t *bias2;
    int32_t multiplier_q30;
} CnnParameters;
typedef struct {
    int32_t fc1_acc[CNN_HIDDEN_COUNT];
    uint8_t fc1_relu[CNN_HIDDEN_COUNT];
    int32_t logits[CNN_CLASS_COUNT];
    unsigned class_id;
} CnnResult;
/* 用 INT64 处理正负舍入，避免负数右移的实现差异。 */
int64_t cnn_round_q30(int64_t product);
int cnn_fc(const uint8_t *features, const CnnParameters *parameters, CnnResult *result);
#endif
