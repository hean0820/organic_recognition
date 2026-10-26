#include "voice_bridge.h"
#include "voice_capture.h"
#include "voice_recognizer.h"
#include <stdlib.h>
#include <string.h>

static void changed(PynqRequest *r) {if(!++r->revision) ++r->revision;}
static void reason(PynqRequest *r,const char *text) {
    if(text!=r->reason) {
        strncpy(r->reason,text ? text:"MODEL_ERROR",sizeof(r->reason)-1);
        r->reason[sizeof(r->reason)-1]=0;
    }
    r->app.reason=r->reason;changed(r);
}
void *psv7_request_create(void) {
    PynqRequest *r=calloc(1,sizeof(*r));
    if(r) {app_init(&r->app);reason(r,r->app.reason);}
    return r;
}
void psv7_request_destroy(void *ptr) {free(ptr);}
int psv7_request_mode(void *ptr,unsigned mode) {
    PynqRequest *r=ptr;int result;
    if(!r || mode>1) return -1;
    result=app_set_mode(&r->app,(AppMode)mode);
    reason(r,r->app.reason);return result;
}
void psv7_request_cancel(void *ptr) {
    PynqRequest *r=ptr;if(!r) return;
    app_cancel(&r->app);reason(r,r->app.reason);
}
void psv7_request_ready(void *ptr,unsigned audio,unsigned model,unsigned line) {
    PynqRequest *r=ptr;if(!r) return;
    r->app.audio_ready=!!audio;r->app.recognizer_ready=!!model;r->app.line_input=!!line;changed(r);
}
int psv7_request_begin(void *ptr,unsigned source) {
    PynqRequest *r=ptr;int result;
    if(!r) return -1;
    result=app_begin(&r->app,(AppSource)source);reason(r,r->app.reason);return result;
}
int psv7_request_current(void *ptr,unsigned source,uint32_t epoch,uint32_t request) {
    PynqRequest *r=ptr;
    return r && r->app.active && epoch==r->app.mode_epoch && epoch==r->app.request_epoch &&
           request==r->app.request_id && ((source==APP_SOURCE_CAMERA && r->app.mode==APP_CAMERA) ||
           (source==APP_SOURCE_VOICE && r->app.mode==APP_VOICE));
}
int psv7_request_progress(void *ptr,unsigned source,uint32_t epoch,uint32_t request,unsigned state,const char *text) {
    PynqRequest *r=ptr;
    if(!psv7_request_current(ptr,source,epoch,request) || state>APP_ERROR) return -1;
    r->app.state=(AppState)state;reason(r,text);return 0;
}
int psv7_request_reject(void *ptr,unsigned source,uint32_t epoch,uint32_t request,unsigned error,const char *text) {
    PynqRequest *r=ptr;
    if(!psv7_request_current(ptr,source,epoch,request)) return -1;
    r->app.active=0;r->app.state=error ? APP_ERROR:APP_REJECTED;
    reason(r,text);app_clear_selection(&r->app,r->reason);changed(r);return 0;
}
int psv7_request_publish(void *ptr,unsigned source,unsigned id,uint32_t epoch,uint32_t request) {
    PynqRequest *r=ptr;int result;
    if(!r) return -1;
    result=app_publish(&r->app,(AppSource)source,id,epoch,request);
    if(!result) reason(r,r->app.reason);
    return result;
}
int psv7_request_voice_result(void *ptr,const Chem22Result *result,uint32_t epoch,uint32_t request) {
    const char *why;
    if(!result || !psv7_request_current(ptr,APP_SOURCE_VOICE,epoch,request)) return -1;
    why=voice_recognizer_reason(result);
    if(!strcmp(why,"OK")) return psv7_request_publish(ptr,APP_SOURCE_VOICE,(unsigned)result->class_id,epoch,request);
    return psv7_request_reject(ptr,APP_SOURCE_VOICE,epoch,request,!strcmp(why,"MODEL_ERROR"),why) ? -1:1;
}
int psv7_request_reference(void *ptr,unsigned id) {
    PynqRequest *r=ptr;int result;
    if(!r) return -1;
    result=app_reference(&r->app,APP_TEST,id);if(!result) reason(r,r->app.reason);return result;
}
const char *psv7_request_reason(void *ptr) {PynqRequest *r=ptr;return r ? r->app.reason:"CLOSED";}
int psv7_request_info(void *ptr,uint32_t *out) {
    PynqRequest *r=ptr;AppControl *a;
    if(!r || !out) return -1;
    a=&r->app;
    out[0]=a->mode;out[1]=a->state;out[2]=a->source;out[3]=a->mode_epoch;
    out[4]=a->request_id;out[5]=a->request_epoch;out[6]=a->selection_seq;out[7]=a->class_id;
    out[8]=(uint32_t)a->valid;out[9]=(uint32_t)a->active;out[10]=(uint32_t)a->audio_ready;
    out[11]=(uint32_t)a->recognizer_ready;out[12]=(uint32_t)a->line_input;out[13]=r->revision;
    return 0;
}
void *psv7_vad_create(void) {
    VoiceCapture *v=calloc(1,sizeof(*v));if(v) voice_capture_start(v);return v;
}
void psv7_vad_destroy(void *ptr) {free(ptr);}
int psv7_vad_feed(void *ptr,const int16_t *pcm,size_t count) {
    VoiceCapture *v=ptr;size_t i;
    if(!v || (!pcm && count)) return -1;
    for(i=0;i<count && voice_capture_active(v);++i) voice_capture_sample(v,pcm[i]);
    return (int)v->state;
}
int psv7_vad_info(void *ptr,uint32_t *out) {
    VoiceCapture *v=ptr;if(!v || !out) return -1;
    out[0]=v->state;out[1]=v->length;out[2]=v->threshold;out[3]=v->noise_abs;
    out[4]=v->peak;out[5]=v->clips;out[6]=v->voiced;return 0;
}
const char *psv7_vad_reason(void *ptr) {VoiceCapture *v=ptr;return v ? v->reason:"CLOSED";}
int psv7_vad_copy(void *ptr,int16_t *pcm,size_t capacity) {
    VoiceCapture *v=ptr;
    if(!v || !pcm || v->state!=VC_DONE || capacity<v->length) return -1;
    memcpy(pcm,v->pcm,v->length*sizeof(*pcm));return (int)v->length;
}
