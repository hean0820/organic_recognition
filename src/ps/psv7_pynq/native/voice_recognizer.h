#ifndef VOICE_RECOGNIZER_H
#define VOICE_RECOGNIZER_H
#include "chem22.h"
#include "ui_panel.h"
/* Operational readiness means the linked candidate passes a numeric self-test;
   it does not mean accuracy or board acceptance has been established. */
int voice_recognizer_init(void);
int voice_recognizer_predict(const int16_t *pcm,size_t count,Chem22Result *result);
/* 0 accepted, 1 rejected, -1 stale/unavailable. Never substitutes class 0. */
int voice_recognizer_apply(UiPanel *ui,const Chem22Result *result,
                           uint32_t epoch,uint32_t request);
const char *voice_recognizer_reason(const Chem22Result *result);
#endif
