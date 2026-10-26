#include "ui_panel.h"
#include "ui_font.h"
#include "mol_board.h"
#include "voice_bridge.h"
#ifdef _WIN32
#include <windows.h>
#endif
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {UiPanel ui; PreviewLayout layout; CameraPipeline camera;uint32_t control_revision;char reason[96];} PynqPageState;
static PynqPageState *live_state;

/* Same names as camera_pipeline.c; no hardware dependency is needed by UI. */
const char *camera_state_name(CameraState state)
{
    static const char *names[]={"WAIT","INPUT_READY","REJECTED","INFER_FAILED","RESULT","CAPTURE_FAILED"};
    return (unsigned)state<6 ? names[state]:"UNKNOWN";
}
static uint64_t native_ticks(void)
{
#ifdef _WIN32
    LARGE_INTEGER value, frequency;
    QueryPerformanceCounter(&value);QueryPerformanceFrequency(&frequency);
    return (uint64_t)((double)value.QuadPart*1000000.0/frequency.QuadPart);
#else
    struct timespec value;clock_gettime(CLOCK_MONOTONIC,&value);
    return (uint64_t)value.tv_sec*1000000U+(uint64_t)value.tv_nsec/1000U;
#endif
}
static uint32_t native_us(void *context){(void)context;return (uint32_t)native_ticks();}
void *psv7_create(void)
{
    PynqPageState *s;
    if(live_state) return 0; /* stage2 model renderer owns one static workspace */
    s=(PynqPageState *)calloc(1,sizeof(PynqPageState));
    if(!s) return 0;
    s->layout=preview_layout(0);ui_init(&s->ui);
    if(mol_board_init()) {free(s);return 0;}
    live_state=s;
    ui_camera_snapshot(&s->ui,&s->camera);
    return s;
}
void psv7_destroy(void *state){if(state && state==live_state) {live_state=0;free(state);}}
const char *psv7_class_name(unsigned id){return id<CHEM_COUNT ? chemicals[id].zh:0;}
unsigned psv7_missing_glyphs(void){return ui_missing_glyphs();}
uint32_t psv7_validate_rgb565(const uint8_t *source,uint32_t pixels)
{
    uint32_t i,bad=0;
    if(!source) return UINT32_MAX;
    /* Exact per-pixel predicate used by the Python checker, in packed BGR. */
    for(i=0;i<pixels;i++,source+=3)
        bad+=((source[0]&7U)|(source[1]&3U)|(source[2]&7U))!=0U;
    return bad;
}
int psv7_render(void *state,const uint8_t *camera,uint8_t *display,unsigned slot,
               unsigned fps10,unsigned frames,uint32_t read_error,uint32_t write_error)
{
    PynqPageState *s=(PynqPageState *)state;
    if(!s || !camera || !display || slot>=3) return -1;
    preview_background(display,&s->layout);
    if(s->ui.app.mode==APP_CAMERA) {
        if(preview_compose(display,1280U*720U*3U,camera,1280U*720U*3U,&s->layout)) return -2;
        preview_camera_roi(display,&s->layout);
        prep_preview_guide(display,&s->layout);
    }
    ui_stats(&s->ui,1,0,fps10,frames,read_error,write_error);
    ui_invalidate(&s->ui); /* Background was rebuilt, so render each panel. */
    {
        uint64_t started=native_ticks();
        int changed=mol_board_update(&s->ui,started,1000000U);
        if(changed<0) return -3;
        if(changed>0) mol_board_render_time((unsigned)(native_ticks()-started));
        if(ui_render(&s->ui,slot,display,1280U*720U*3U,&s->layout)<0) return -4;
        if(mol_board_composite(display,1280U*720U*3U,&s->layout)<0) return -5;
        return 1;
    }
}
int psv7_postprocess(void *state,const uint8_t *detect,const uint8_t *gray,
                    const uint8_t *ink,uint8_t *out,uint32_t *report)
{
    PynqPageState *s=(PynqPageState *)state;
    PrepReport r;PrepClock timer={0,native_us};PrepCode code;
    if(!s || !detect || !gray || !ink || !out || !report) return -1;
    memcpy(s->camera.work.detection,detect,PREP_DETECT_N);
    memcpy(s->camera.work.gray,gray,PREP_WORK_N);
    memcpy(s->camera.work.ink,ink,PREP_WORK_N);
    code=prep_from_filtered(&s->camera.work,out,&r,&timer);
    memcpy(report,&r,sizeof(r));return (int)code;
}
PrepCode psv7_prep_from_filtered_reference(PrepWorkspace *,uint8_t *,PrepReport *,const PrepClock *);
int psv7_postprocess_reference(void *state,const uint8_t *detect,const uint8_t *gray,
                    const uint8_t *ink,uint8_t *out,uint32_t *report)
{
    PynqPageState *s=(PynqPageState *)state;
    PrepReport r;PrepClock timer={0,native_us};PrepCode code;
    if(!s || !detect || !gray || !ink || !out || !report) return -1;
    memcpy(s->camera.work.detection,detect,PREP_DETECT_N);
    memcpy(s->camera.work.gray,gray,PREP_WORK_N);
    memcpy(s->camera.work.ink,ink,PREP_WORK_N);
    code=psv7_prep_from_filtered_reference(&s->camera.work,out,&r,&timer);
    memcpy(report,&r,sizeof(r));return (int)code;
}
void psv7_begin(void *state){ui_camera_begin(&((PynqPageState *)state)->ui);}
void psv7_clear(void *state)
{
    PynqPageState *s=(PynqPageState *)state;
    unsigned sequence=s->camera.capture_sequence;
    app_cancel(&s->ui.app);
    s->control_revision=0;
    memset(&s->camera,0,sizeof(s->camera));s->camera.capture_sequence=sequence;
    ui_camera_snapshot(&s->ui,&s->camera);
}
int psv7_select(void *state,unsigned id){return ui_test_select(&((PynqPageState *)state)->ui,id);}
void psv7_publish(void *state,const uint8_t *input,const uint32_t *report,const uint32_t *tx)
{
    PynqPageState *s=(PynqPageState *)state;CameraPipeline *c=&s->camera;
    memcpy(c->input,input,4096);memcpy(&c->prep,report,sizeof(PrepReport));
    memset(&c->inference,0,sizeof(c->inference));
    c->state=(CameraState)tx[0];c->classify=(int)tx[1];c->captured=(int)tx[2];
    c->inference.result.class_id=tx[3];c->inference.transfer.sequence=tx[4];
    c->inference.transfer.cycles=tx[5];c->inference.transfer.input_count=tx[6];
    c->inference.transfer.output_count=tx[7];c->inference.transfer.error=tx[8];
    c->total_us=tx[9];c->inference.fc_us=tx[10];c->inference.status=(int32_t)tx[11];
    c->capture_sequence=tx[12];c->inference.valid=c->state==CAMERA_RESULT && c->inference.status==0;
    ui_camera_snapshot(&s->ui,c);
}
int psv7_fc(const uint8_t *features,const int8_t *w1,const int32_t *b1,
           const int8_t *w2,const int32_t *b2,int32_t multiplier,
           int32_t *acc,uint8_t *hidden,int32_t *logits,uint32_t *info)
{
    CnnParameters parameters={w1,b1,w2,b2,multiplier};CnnResult result;
    uint32_t start=native_us(0);int status=cnn_fc(features,&parameters,&result);
    info[1]=native_us(0)-start;
    if(status) return status;
    memcpy(acc,result.fc1_acc,sizeof(result.fc1_acc));
    memcpy(hidden,result.fc1_relu,sizeof(result.fc1_relu));
    memcpy(logits,result.logits,sizeof(result.logits));info[0]=result.class_id;return 0;
}

int psv7_model_info(void *state,uint32_t *out)
{
    const MolBoardStats *m=mol_board_stats();
    PynqPageState *s=(PynqPageState *)state;
    if(!s || s!=live_state || !out) return -1;
    out[0]=m->active;out[1]=m->class_id;out[2]=m->paused;
    out[3]=m->renders;out[4]=m->presents;out[5]=m->render_us_last;
    out[6]=m->render_errors;out[7]=(uint32_t)(m->angle*1000.0f);
    out[8]=s->ui.app.valid;out[9]=(uint32_t)s->ui.app.source;
    return 0;
}
int psv7_model_pause(void *state)
{
    if(!state || state!=live_state) return -1;
    mol_board_pause_toggle();return 0;
}
int psv7_model_reset(void *state)
{
    if(!state || state!=live_state) return -1;
    mol_board_reset();return 0;
}
void psv7_presented(void *state){if(state && state==live_state) mol_board_presented();}

int psv7_sync_control(void *state,void *request)
{
    PynqPageState *s=state;PynqRequest *r=request;AppMode old_mode;
    if(!s || s!=live_state || !r) return -1;
    if(s->control_revision==r->revision) return 0;
    old_mode=s->ui.app.mode;s->ui.app=r->app;
    strncpy(s->reason,r->app.reason,sizeof(s->reason)-1);s->reason[sizeof(s->reason)-1]=0;
    s->ui.app.reason=s->reason;s->control_revision=r->revision;
    if(old_mode!=s->ui.app.mode || !strcmp(s->reason,"CANCELLED")) {
        s->ui.preprocess_active=0;s->ui.camera_valid=0;s->ui.demo_class=0;
        s->ui.demo_status=0;s->ui.auto_demo=0;
        ui_app_refresh(&s->ui);
    } else if(s->ui.app.mode==APP_VOICE) ui_app_refresh(&s->ui);
    ui_invalidate(&s->ui);return 0;
}

int psv7_audio_stats(void *state,unsigned peak,unsigned noise,unsigned samples,unsigned dropped)
{
    PynqPageState *s=state;
    if(!s || s!=live_state) return -1;
    s->ui.audio_level=peak;s->ui.audio_noise=noise;s->ui.audio_samples=samples;s->ui.audio_dropped=dropped;
    ui_invalidate(&s->ui);return 0;
}

/* Call only after synchronizing the authoritative controller under its lock. */
int psv7_voice_timing(void *state,uint32_t epoch,uint32_t request,
                     uint32_t total,uint32_t frontend,uint32_t cnn,uint32_t reference)
{
    PynqPageState *s=state;
    if(!s || s!=live_state) return -1;
    if(ui_voice_timing(&s->ui,epoch,request,total,frontend,cnn)) return -1;
    s->ui.voice_timing_reference=reference!=0;return 0;
}

int psv7_voice_timing_info(void *state,uint32_t *out)
{
    PynqPageState *s=state;
    if(!s || s!=live_state || !out) return -1;
    out[0]=s->ui.voice_total_us;out[1]=s->ui.voice_frontend_us;out[2]=s->ui.voice_cnn_us;
    out[3]=s->ui.voice_timing_epoch;out[4]=s->ui.voice_timing_request;
    out[5]=s->ui.voice_timing_selection_seq;out[6]=(uint32_t)s->ui.voice_timing_valid;
    out[7]=(uint32_t)s->ui.voice_timing_reference;return 0;
}

/* Additive diagnostics only. The original psv7_render above is unchanged.
 * Each timing region is disjoint; returned total includes instrumentation.
 * The original render path is used for every alternate control frame. */
int psv7_render_profiled(void *state,const uint8_t *camera,uint8_t *display,unsigned slot,
                        unsigned fps10,unsigned frames,uint32_t read_error,uint32_t write_error,
                        uint64_t *timing)
{
    PynqPageState *s=(PynqPageState *)state;
    uint64_t start,t0,t1,t2,t3,t4;
    int changed;
    if(!s || !camera || !display || slot>=3 || !timing) return -1;
    start=native_ticks();
    preview_background(display,&s->layout);
    if(s->ui.app.mode==APP_CAMERA) {
        if(preview_compose(display,1280U*720U*3U,camera,1280U*720U*3U,&s->layout)) return -2;
        preview_camera_roi(display,&s->layout);
        prep_preview_guide(display,&s->layout);
    }
    ui_stats(&s->ui,1,0,fps10,frames,read_error,write_error);
    ui_invalidate(&s->ui);
    t0=native_ticks();
    changed=mol_board_update(&s->ui,t0,1000000U);
    if(changed<0) return -3;
    if(changed>0) mol_board_render_time((unsigned)(native_ticks()-t0));
    t1=native_ticks();
    if(ui_render(&s->ui,slot,display,1280U*720U*3U,&s->layout)<0) return -4;
    t2=native_ticks();
    if(mol_board_composite(display,1280U*720U*3U,&s->layout)<0) return -5;
    t3=native_ticks();
    timing[0]=t0-start;timing[1]=t1-t0;timing[2]=t2-t1;
    timing[3]=t3-t2;
    t4=native_ticks();timing[4]=t4-start;
    return 1;
}
