#ifndef CHEM22_H
#define CHEM22_H
#include <stddef.h>
#include <stdint.h>
#define CHEM22_CLASS_COUNT 22
#define CHEM22_MAX_SAMPLES 48000
#define CHEM22_FEATURES 3840
typedef struct {
    int class_id; /* -1 = rejected; 0 is a valid ethylene result */
    int raw_class; /* 22 unknown, 23 silence */
    float confidence;
    float margin;
    int reason; /* 0 accepted, 1 unknown/low score, 2 silence, 3 invalid input */
} Chem22Result;
/* 16 kHz mono signed 16-bit PCM; max 3 seconds. Static workspace: not reentrant. */
int chem22_predict_pcm(const int16_t *pcm,size_t count,Chem22Result *result);
int chem22_frontend(const int16_t *pcm,size_t count,float *features);
void chem22_logits(const float *features,float *logits24);
const char *chem22_model_version(void);
typedef struct {uint32_t frontend_us,cnn_us,postprocess_us,total_us;} Chem22Profile;
/* Last call only; like the static inference workspace, not reentrant. */
const Chem22Profile *chem22_last_profile(void);
#endif
