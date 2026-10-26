#ifndef VOICE_CAPTURE_H
#define VOICE_CAPTURE_H
#include <stdint.h>
#define VOICE_RATE 16000U
#define VOICE_FRAME 160U
#define VOICE_PREROLL 3200U
#define VOICE_MAX_SAMPLES 48000U
typedef enum {VC_IDLE,VC_CALIBRATE,VC_WAIT,VC_SPEECH,VC_DONE,VC_REJECT} VoiceState;
typedef struct {
    VoiceState state;const char *reason;
    int16_t pcm[VOICE_MAX_SAMPLES],preroll[VOICE_PREROLL];
    unsigned length,ring_pos,ring_count,frames,frame_count,onset,voiced,silence,fixed_diagnostic;
    uint32_t frame_abs,noise_abs,threshold,peak,clips;
    int32_t dc_q8;
} VoiceCapture;
void voice_capture_start(VoiceCapture *v);
/* Unsegmented raw PCM for inspecting VAD failures; never an accepted ASR result. */
void voice_capture_start_fixed(VoiceCapture *v);
void voice_capture_cancel(VoiceCapture *v);
void voice_capture_sample(VoiceCapture *v,int16_t sample);
int voice_capture_active(const VoiceCapture *v);
#endif
