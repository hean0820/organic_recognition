#include "voice_capture.h"
#include <string.h>
int voice_capture_active(const VoiceCapture *v) {
    return v->state==VC_CALIBRATE || v->state==VC_WAIT || v->state==VC_SPEECH;
}
void voice_capture_cancel(VoiceCapture *v) {v->state=VC_IDLE;v->length=0;v->reason="CANCELLED";}
void voice_capture_start(VoiceCapture *v) {
    memset(v,0,sizeof(*v));v->state=VC_CALIBRATE;v->reason="KEEP_QUIET_500MS";
}
void voice_capture_start_fixed(VoiceCapture *v) {
    memset(v,0,sizeof(*v));v->fixed_diagnostic=1;v->state=VC_SPEECH;v->reason="DIAGNOSTIC_RECORDING_3S";
}
static void reject(VoiceCapture *v,const char *why) {v->state=VC_REJECT;v->reason=why;v->length=0;}
void voice_capture_sample(VoiceCapture *v,int16_t sample) {
    unsigned magnitude,mean,i;
    int filtered;
    if(!voice_capture_active(v)) return;
    v->dc_q8+=((int32_t)sample*256-v->dc_q8)/256;
    filtered=(int)sample-v->dc_q8/256;
    if(filtered>32767) filtered=32767;
    if(filtered<-32768) filtered=-32768;
    magnitude=(unsigned)(filtered<0 ? -filtered:filtered);
    v->frame_abs+=magnitude;
    if(magnitude>v->peak) v->peak=magnitude;
    if(sample>=32760 || sample<=-32760) ++v->clips;
    if(v->fixed_diagnostic) {
        v->pcm[v->length++]=sample;
        if(v->length==VOICE_MAX_SAMPLES) {v->state=VC_DONE;v->reason="DIAGNOSTIC_CAPTURE_READY_NO_ASR";}
        return;
    }
    /* Preserve raw PCM for the trained frontend; DC-blocked samples are used
       only by VAD. The model subtracts the utterance's global mean itself. */
    v->preroll[v->ring_pos]=sample;
    v->ring_pos=(v->ring_pos+1U)%VOICE_PREROLL;
    if(v->ring_count<VOICE_PREROLL) ++v->ring_count;
    if(v->state==VC_SPEECH) {
        if(v->length>=VOICE_MAX_SAMPLES) {reject(v,"TOO_LONG");return;}
        v->pcm[v->length++]=sample;
    }
    if(++v->frame_count<VOICE_FRAME) return;
    v->frame_count=0;mean=v->frame_abs/VOICE_FRAME;v->frame_abs=0;++v->frames;
    if(v->state==VC_CALIBRATE) {
        v->noise_abs+=mean;
        if(v->frames==50) {
            v->noise_abs/=50;v->threshold=v->noise_abs*3U+100U;
            if(v->threshold<250) v->threshold=250;
            v->state=VC_WAIT;v->reason="SPEAK_NOW";v->frames=0;v->peak=0;v->clips=0;
        }
    } else if(v->state==VC_WAIT) {
        v->onset=mean>v->threshold ? v->onset+1U:0;
        if(v->onset>=3) {
            v->state=VC_SPEECH;v->reason="LISTENING";v->frames=0;v->voiced=3;
            for(i=0;i<v->ring_count;++i) v->pcm[i]=v->preroll[(v->ring_pos+VOICE_PREROLL-v->ring_count+i)%VOICE_PREROLL];
            v->length=v->ring_count;
        } else if(v->frames>=500) reject(v,"NO_SPEECH");
    } else {
        if(mean>v->threshold) {++v->voiced;v->silence=0;}
        else ++v->silence;
        if(v->silence>=60) {
            if(v->voiced<15) {reject(v,"TOO_SHORT");return;}
            if(v->clips>VOICE_RATE/100U) {reject(v,"CLIPPED");return;}
            v->length-=50U*VOICE_FRAME; // Keep 100 ms trailing silence.
            v->state=VC_DONE;v->reason="CAPTURE_READY";
        }
    }
}
