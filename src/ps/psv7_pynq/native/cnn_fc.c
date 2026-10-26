#include "cnn_fc.h"
#include <limits.h>
#include <stddef.h>

int64_t cnn_round_q30(int64_t product)
{
    uint64_t magnitude = product >= 0 ? (uint64_t)product : (uint64_t)(-(product+1))+1U;
    int64_t rounded = (int64_t)((magnitude + (UINT64_C(1)<<29)) >> 30);
    return product >= 0 ? rounded : -rounded;
}

int cnn_fc(const uint8_t *features, const CnnParameters *p, CnnResult *r)
{
    unsigned output, input;
    if (!features || !p || !r || !p->weight1 || !p->bias1 ||
        !p->weight2 || !p->bias2 || p->multiplier_q30 <= 0) return -1;
    for (input = 0; input < CNN_FEATURE_BYTES; ++input)
        if (features[input] > 127U) return -2;
    for (output = 0; output < CNN_HIDDEN_COUNT; ++output) {
        /* 全部输入乘加和偏置完成后，仅量化一次。 */
        int64_t acc = p->bias1[output];
        int64_t activated;
        const int8_t *row = p->weight1 + output * CNN_FEATURE_BYTES;
        for (input = 0; input < CNN_FEATURE_BYTES; ++input)
            acc += (int32_t)features[input] * (int32_t)row[input];
        if (acc < INT32_MIN || acc > INT32_MAX) return -3;
        r->fc1_acc[output] = (int32_t)acc;
        activated = cnn_round_q30(acc * p->multiplier_q30);
        r->fc1_relu[output] = activated < 0 ? 0U : activated > 127 ? 127U : (uint8_t)activated;
    }
    r->class_id = 0;
    for (output = 0; output < CNN_CLASS_COUNT; ++output) {
        int64_t acc = p->bias2[output];
        const int8_t *row = p->weight2 + output * CNN_HIDDEN_COUNT;
        for (input = 0; input < CNN_HIDDEN_COUNT; ++input)
            acc += (int32_t)r->fc1_relu[input] * (int32_t)row[input];
        if (acc < INT32_MIN || acc > INT32_MAX) return -3;
        r->logits[output] = (int32_t)acc;
        if (r->logits[output] > r->logits[r->class_id]) r->class_id = output;
    }
    return 0;
}
