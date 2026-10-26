#include "ui_panel.h"
#include "ui_font.h"
#include "ui_font_extra.h"
#include "mol_selection.h"
#include <string.h>
#include <stdio.h>

static unsigned missing_glyphs;
static const char *status_text[UI_STATUS_COUNT] = {
    "等待识别", "采集中", "预处理中", "推理中", "识别完成", "未检测到笔迹", "错误"
};

static void changed(UiPanel *u)
{
    ++u->revision;
    if (!u->revision) {u->revision=1; memset(u->slot_revision,0,sizeof(u->slot_revision));}
}
void ui_init(UiPanel *u)
{
    memset(u,0,sizeof(*u)); app_init(&u->app);u->revision=1; u->demo_class=1; u->status=UI_WAIT;
}
static int voice_timing_current(const UiPanel *u)
{
    return u->voice_timing_valid && u->app.mode==APP_VOICE && !u->app.active &&
           u->voice_timing_epoch==u->app.mode_epoch &&
           u->voice_timing_request==u->app.request_id &&
           u->voice_timing_selection_seq==u->app.selection_seq;
}
void ui_app_refresh(UiPanel *u) {
    if(!voice_timing_current(u)) u->voice_timing_valid=0;
    u->class_id=u->app.valid ? u->app.class_id:0;
    if(u->app.source==APP_EXTERNAL) u->result_source=UI_SOURCE_EXTERNAL;
    else if(u->app.source==APP_TEST) u->result_source=UI_SOURCE_TEST;
    else if(u->app.mode==APP_VOICE) u->result_source=UI_SOURCE_VOICE;
    else if(u->app.source==APP_NONE) u->result_source=UI_SOURCE_CAMERA;
    if(u->app.valid) u->status=UI_DONE;
    else u->status=u->app.state==APP_ERROR ? UI_ERROR:UI_WAIT;
    changed(u);
}
int ui_voice_timing(UiPanel *u,uint32_t epoch,uint32_t request,
                    uint32_t total_us,uint32_t frontend_us,uint32_t cnn_us)
{
    if(!u || u->app.mode!=APP_VOICE || !u->app.recognizer_ready || u->app.active ||
       epoch!=u->app.mode_epoch || epoch!=u->app.request_epoch ||
       request!=u->app.request_id ||
       (u->app.state!=APP_RESULT && u->app.state!=APP_REJECTED && u->app.state!=APP_ERROR) ||
       (u->app.source!=APP_NONE && u->app.source!=APP_SOURCE_VOICE)) return -1;
    u->voice_total_us=total_us;u->voice_frontend_us=frontend_us;u->voice_cnn_us=cnn_us;
    u->voice_timing_epoch=epoch;u->voice_timing_request=request;
    u->voice_timing_selection_seq=u->app.selection_seq;u->voice_timing_valid=1;
    changed(u);return 0;
}
void ui_mode(UiPanel *u,AppMode mode) {
    if(app_set_mode(&u->app,mode)<=0) return;
    u->auto_demo=0;u->preprocess_active=0;u->camera_valid=0;u->demo_class=0;
    u->demo_status=0;u->result_source=mode==APP_VOICE ? UI_SOURCE_VOICE:UI_SOURCE_CAMERA;
    ui_app_refresh(u);
}
int ui_test_select(UiPanel *u,unsigned id) {
    if(app_reference(&u->app,APP_TEST,id)) return -1;
    u->auto_demo=0;u->preprocess_active=0;u->camera_valid=0;u->demo_class=0;
    ui_app_refresh(u);return 0;
}
int ui_voice_class(UiPanel *u,unsigned id) {
    if(!u || app_reference(&u->app,APP_EXTERNAL,id)) return -1;
    u->auto_demo=0;u->preprocess_active=0;u->camera_valid=0;u->demo_class=0;
    ui_app_refresh(u);return 0;
}
void ui_invalidate(UiPanel *u) {memset(u->slot_revision,0,sizeof(u->slot_revision));}
int ui_demo_class(UiPanel *u, unsigned id)
{
    if (!u || id>=CHEM_COUNT) return -1;
    if(app_reference(&u->app,APP_DEMO,id)) return -1;
    u->class_id=id;u->demo_class=1;u->camera_valid=0;u->result_source=UI_SOURCE_DEMO;changed(u);
    return 0;
}
int ui_result(UiPanel *u, unsigned id, unsigned sequence)
{
    if (!u || id>=CHEM_COUNT) return -1;
    if(app_reference(&u->app,APP_GOLDEN,id)) return -1;
    u->class_id=id; u->sequence=sequence;u->demo_class=0;
    u->camera_valid=0;u->result_source=UI_SOURCE_GOLDEN;
    u->demo_status=0;u->status=UI_DONE;changed(u);return 0;
}
int ui_status(UiPanel *u, UiStatus status, int demo)
{
    if(!u || (unsigned)status>=UI_STATUS_COUNT) return -1;
    if(u->app.mode==APP_VOICE) return 0;
    if(status!=UI_DONE && u->app.valid) app_clear_selection(&u->app,"NO_CURRENT_RESULT");
    if(u->status!=status || u->demo_status!=!!demo) {
        u->status=status;u->demo_status=!!demo;changed(u);
        if(demo) {u->result_source=UI_SOURCE_DEMO;u->demo_class=1;u->camera_valid=0;}
        else if(status!=UI_DONE && u->result_source==UI_SOURCE_CAMERA) {
            u->camera_valid=0;
            if(status==UI_ERROR) u->camera_state=CAMERA_CAPTURE_FAILED;
        }
    }
    return 0;
}
void ui_auto(UiPanel *u, int enabled)
{
    if(u->auto_demo!=!!enabled) {u->auto_demo=!!enabled;changed(u);}
}
void ui_stats(UiPanel *u, int sensor_ok, int bars, unsigned fps, unsigned frames,
              uint32_t re, uint32_t we)
{
    if(u->sensor_ok!=!!sensor_ok || u->bars!=!!bars || u->fps_x10!=fps ||
       u->frames!=frames || u->read_errors!=re || u->write_errors!=we) {
        u->sensor_ok=!!sensor_ok;u->bars=!!bars;u->fps_x10=fps;u->frames=frames;
        u->read_errors=re;u->write_errors=we;changed(u);
    }
}
unsigned ui_missing_glyphs(void) {return missing_glyphs;}
void ui_preprocess_result(UiPanel *u,const uint8_t *input,const PrepReport *report,unsigned sequence)
{
    if(u->app.mode!=APP_CAMERA) return;
    u->app.active=0;app_clear_selection(&u->app,"PREPROCESS_ONLY");
    u->preprocess_active=1;u->preprocess_sequence=sequence;u->preprocess_report=*report;
    if(report->code==PREP_OK) memcpy(u->preprocess_input,input,4096);
    else memset(u->preprocess_input,0,4096);
    u->demo_class=1;u->demo_status=0;
    u->result_source=UI_SOURCE_PREPROCESS;u->camera_valid=0;
    u->status=report->code==PREP_OK ? UI_DONE:report->code==PREP_BLANK ? UI_BLANK:UI_ERROR;
    changed(u);
}
void ui_camera_begin(UiPanel *u)
{
    if(u->app.mode!=APP_CAMERA) return;
    if(!u->app.active) app_begin(&u->app,APP_SOURCE_CAMERA);
    u->preprocess_active=1;u->result_source=UI_SOURCE_CAMERA;u->camera_valid=0;
    u->demo_class=1;u->demo_status=0;u->status=UI_CAPTURE;
    memset(u->preprocess_input,0,4096);memset(&u->camera_inference,0,sizeof(u->camera_inference));
    u->camera_total_us=0;changed(u);
}
void ui_golden_begin(UiPanel *u)
{
    if(u->app.mode!=APP_CAMERA) return;
    app_cancel(&u->app);u->app.reason="GOLDEN_TEST";
    u->preprocess_active=0;u->result_source=UI_SOURCE_GOLDEN;u->camera_valid=0;
    u->demo_class=1;u->demo_status=0;u->status=UI_WAIT;changed(u);
}
void ui_camera_snapshot(UiPanel *u,const CameraPipeline *camera)
{
    int valid=camera->state==CAMERA_RESULT && camera->captured && camera->classify &&
              camera->prep.code==PREP_OK && camera->inference.valid && camera->inference.status==0 &&
              camera->inference.result.class_id<CHEM_COUNT;
    if(u->app.mode!=APP_CAMERA) return;
    if(valid) {
        if(app_publish(&u->app,APP_SOURCE_CAMERA,camera->inference.result.class_id,
                       u->app.request_epoch,u->app.request_id)) valid=0;
    } else {
        u->app.active=0;u->app.state=APP_IDLE;
        app_clear_selection(&u->app,camera->state==CAMERA_WAIT ? "WAIT":"CAMERA_NO_RESULT");
    }
    u->preprocess_active=1;u->preprocess_sequence=camera->capture_sequence;
    u->preprocess_report=camera->prep;
    u->camera_state=camera->state==CAMERA_RESULT && !valid ? CAMERA_INFER_FAILED:camera->state;
    u->camera_inference=camera->inference;u->camera_total_us=camera->total_us;
    if(camera->state!=CAMERA_RESULT && camera->state!=CAMERA_INFER_FAILED)
        memset(&u->camera_inference,0,sizeof(u->camera_inference));
    if(camera->captured && camera->prep.code==PREP_OK) memcpy(u->preprocess_input,camera->input,4096);
    else memset(u->preprocess_input,0,4096);
    u->camera_valid=valid;u->demo_status=0;u->demo_class=!valid;
    u->result_source=camera->classify || camera->state==CAMERA_WAIT ? UI_SOURCE_CAMERA:UI_SOURCE_PREPROCESS;
    if(valid) {u->class_id=camera->inference.result.class_id;u->sequence=camera->inference.transfer.sequence;}
    if(valid || camera->state==CAMERA_INPUT_READY) u->status=UI_DONE;
    else if(camera->state==CAMERA_WAIT) u->status=UI_WAIT;
    else if(camera->state==CAMERA_REJECTED && camera->prep.code==PREP_BLANK) u->status=UI_BLANK;
    else u->status=UI_ERROR;
    changed(u);
}

static void pixel(uint8_t *d, unsigned stride, unsigned x, unsigned y, uint8_t shade)
{
    size_t offset=((size_t)y*stride+x)*3U;
    d[offset]=shade;d[offset+1]=shade;d[offset+2]=shade;
}
static void rect(uint8_t *d, unsigned stride, unsigned x, unsigned y,
                 unsigned w,unsigned h,uint8_t shade)
{
    unsigned row;
    for(row=0;row<h;++row)
        memset(d+((size_t)(y+row)*stride+x)*3U,shade,(size_t)w*3U);
}
static uint32_t decode(const char **s)
{
    const unsigned char *p=(const unsigned char *)*s;
    uint32_t cp; unsigned n,i;
    if(p[0]<0x80) {(*s)++;return p[0];}
    if((p[0]&0xe0)==0xc0) {cp=p[0]&0x1f;n=2;}
    else if((p[0]&0xf0)==0xe0) {cp=p[0]&0x0f;n=3;}
    else if((p[0]&0xf8)==0xf0) {cp=p[0]&7;n=4;}
    else {(*s)++;return '?';}
    for(i=1;i<n;++i) {
        if(!p[i] || (p[i]&0xc0)!=0x80) {(*s)++;return '?';}
        cp=(cp<<6)|(p[i]&0x3f);
    }
    *s+=n; return cp;
}
static const UiGlyph *glyph(unsigned size, uint32_t cp)
{
    unsigned lo=0,hi=ui_glyph_count;
    uint32_t key=(size<<21)|cp;
    while(lo<hi) {
        unsigned mid=lo+(hi-lo)/2;
        const UiGlyph *g=&ui_glyphs[mid];
        uint32_t k=((unsigned)g->size<<21)|g->codepoint;
        if(k<key) lo=mid+1;else hi=mid;
    }
    if(lo<ui_glyph_count && ui_glyphs[lo].size==size && ui_glyphs[lo].codepoint==cp)
        return &ui_glyphs[lo];
    lo=0;hi=ui_extra_glyph_count;
    while(lo<hi) {
        unsigned mid=lo+(hi-lo)/2;
        const UiGlyph *g=&ui_extra_glyphs[mid];
        uint32_t k=((unsigned)g->size<<21)|g->codepoint;
        if(k<key) lo=mid+1;else hi=mid;
    }
    if(lo<ui_extra_glyph_count && ui_extra_glyphs[lo].size==size && ui_extra_glyphs[lo].codepoint==cp)
        return &ui_extra_glyphs[lo];
    ++missing_glyphs;
    return cp=='?' ? 0:glyph(size,'?');
}
/* All text is clipped to a declared region, with optional wrapping. */
static void text(uint8_t *d,unsigned stride,unsigned x,unsigned y,unsigned w,unsigned h,
                 const char *s,unsigned size,uint8_t shade,int wrap)
{
    unsigned cx=x,cy=y;
    while(*s) {
        uint32_t cp=decode(&s);
        const UiGlyph *g;
        unsigned gx,gy,rowbytes;
        if(cp=='\n') {cx=x;cy+=size+5U;continue;}
        g=glyph(size,cp);if(!g) continue;
        if(cx+g->advance>x+w) {
            if(!wrap) break;
            cx=x;cy+=size+5U;
        }
        if(cy+g->height>y+h) break;
        rowbytes=(g->width+7U)/8U;
        for(gy=0;gy<g->height;++gy)
            for(gx=0;gx<g->width && cx+gx<x+w;++gx)
                if(((g->offset & UI_EXTRA_FLAG) ? ui_extra_font_bits:ui_font_bits)
                   [(g->offset & ~UI_EXTRA_FLAG)+gy*rowbytes+gx/8U]&(0x80U>>(gx%8U)))
                    pixel(d,stride,cx+gx,cy+gy,shade);
        cx+=g->advance;
    }
}

int ui_render(UiPanel *u,unsigned slot,uint8_t *d,size_t bytes,const PreviewLayout *p)
{
    const Chemical *c;
    char line[200];
    unsigned r, info_y, status_y;
    int show_class;
    if(!u || !d || !p || slot>=3 || p->width!=1280 || p->height!=720 ||
       bytes<1280U*720U*3U || p->camera_x!=16 || p->camera_y!=16 ||
       p->camera_width!=768 || p->camera_height!=432 ||
       u->class_id>=CHEM_COUNT || u->status>=UI_STATUS_COUNT) return -1;
    /* A fresh camera frame may arrive with unchanged UI revision. Redraw the
       camera-only frame before the cache check; voice rendering clears it. */
    if(u->app.mode==APP_CAMERA) preview_camera_roi(d,p);
    if(u->slot_revision[slot]==u->revision) return 0;
    molecule_sync(u);
    show_class=molecule_selection()->class_id>=0;
    c=&chemicals[show_class ? (unsigned)molecule_selection()->class_id:u->class_id];
    /* Camera ROI is drawn above; the remaining UI does not alter its interior. */
    rect(d,1280,800,16,464,304,0x24);
    rect(d,1280,800,336,464,368,0x1c);
    rect(d,1280,16,464,768,240,0x20);
    rect(d,1280,800,16,4,304,0xc0);
    rect(d,1280,16,464,768,2,0x80);
    text(d,1280,820,24,424,22,u->result_source==UI_SOURCE_CAMERA ?
        (molecule_selection()->pending ? "Previous model / Updating":u->camera_valid && u->status==UI_DONE ? "Camera recognition result":"Camera / No valid result"):
        u->result_source==UI_SOURCE_GOLDEN ? "Golden test / Not camera":
        u->result_source==UI_SOURCE_DEMO ? "Reference info / Demo":
        u->result_source==UI_SOURCE_EXTERNAL ? "External ID / NOT onboard recognition":
        u->result_source==UI_SOURCE_TEST ? "TEST injection / NOT speech recognition":
        u->result_source==UI_SOURCE_VOICE ? (u->app.valid ? "Voice recognition result":show_class ? "Previous confirmed result":"Voice / No valid result"):
        "Input preview / Not recognition",14,0xd0,0);
    if(show_class) {
    text(d,1280,820,50,300,42,c->zh,32,0xf4,0);
    snprintf(line,sizeof(line),"%02u / 21",(unsigned)molecule_selection()->class_id);
    text(d,1280,1148,62,96,22,line,14,0xb0,0);
    text(d,1280,820,95,424,26,c->en,20,0xcc,0);
    snprintf(line,sizeof(line),"分子式  %s",c->formula);
    text(d,1280,820,126,424,26,line,20,0xf0,0);
    snprintf(line,sizeof(line),"结构简式  %s",c->structure);
    text(d,1280,820,155,424,25,line,14,0xba,0);
    info_y=188;
    snprintf(line,sizeof(line),"物理：%s",c->physical);
    text(d,1280,820,info_y,424,26,line,20,0xe0,0);
    snprintf(line,sizeof(line),"化学：%s",c->chemical);
    text(d,1280,820,info_y+30,424,26,line,20,0xe0,0);
    snprintf(line,sizeof(line),"用途：%s",c->uses);
    text(d,1280,820,info_y+60,424,26,line,20,0xe0,0);
    text(d,1280,820,286,424,22,"物态条件：20℃、约1 atm、纯物质",14,0x9a,0);
    } else {
        text(d,1280,820,66,424,42,u->app.mode==APP_VOICE ? "等待语音识别":u->status==UI_BLANK ? "未检测到笔迹":u->status==UI_ERROR ? "错误":"等待识别",20,0xf4,0);
        if(u->app.mode==APP_VOICE) {
            text(d,1280,820,132,424,26,"麦克风采音已接入",20,0xcc,0);
            text(d,1280,820,174,424,26,u->app.recognizer_ready ? "ASR model ready":"ASR model unavailable",14,0xb0,0);
            text(d,1280,820,224,424,44,"Start one voice request from PC or Notebook.",14,0xb0,1);
        } else {
        text(d,1280,820,132,424,26,"e / Space: capture and recognize",20,0xcc,0);
        text(d,1280,820,174,424,26,"22 trained classes",20,0xb0,0);
        text(d,1280,820,224,424,44,"Keep all strokes inside the dashed guide.",14,0xb0,1);
        }
    }

    text(d,1280,824,358,416,30,"分子空间结构",20,0xe0,0);
    rect(d,1280,824,397,416,1,0x50);
    if(show_class) {
        /* size=14 glyphs occupy 20 rows. Keep the complete help line below
           the 256-row model blit [420,676), with a four-row gap. */
        text(d,1280,824,680,416,20,molecule_selection()->pending ?
            "Updating model":"app.pause_3d() / app.reset_3d()",14,0xc0,0);
    } else {
        text(d,1280,824,462,416,30,"Waiting for a valid result",20,0xd0,0);
        text(d,1280,824,510,416,26,"app.recognize()",14,0xb0,0);
        text(d,1280,824,608,416,24,u->app.mode==APP_VOICE ? "Waiting for voice recognition":"Waiting for camera recognition",14,0x98,0);
    }

    text(d,1280,36,482,720,28,u->app.mode==APP_VOICE ? "化学名称语音识别":"手写有机物化学式识别",20,0xf0,0);
    if(u->app.mode==APP_VOICE) {
        rect(d,1280,16,16,768,432,0x18);
        rect(d,1280,36,36,728,60,0xc8);
        text(d,1280,52,44,680,46,"语音识别模式",32,0x12,0);
        text(d,1280,52,126,680,40,u->app.line_input ? "外接 LINE_IN  /  单次触发":"板载麦克风  /  单次触发",20,0xf0,0);
        text(d,1280,52,180,680,32,"按一次开始，只识别一个名称",20,0xc0,0);
        text(d,1280,52,232,680,54,u->app.valid ? chemicals[u->app.class_id].zh:"等待语音识别",32,0xf0,0);
        text(d,1280,52,300,680,30,u->result_source==UI_SOURCE_TEST ?
             "测试注入结果，不是真实语音识别":
             u->result_source==UI_SOURCE_EXTERNAL ? "外部编号输入，不是板载识别":
             u->app.recognizer_ready ? "单次识别":"识别模型尚未接入",20,0xf0,0);
        snprintf(line,sizeof(line),"State: %s / %s",app_state_name(u->app.state),u->app.reason);
        text(d,1280,52,358,680,32,line,20,0xc0,0);
        snprintf(line,sizeof(line),"Peak:%u  Noise:%u  Samples:%u  Dropped:%u",u->audio_level,u->audio_noise,u->audio_samples,u->audio_dropped);
        text(d,1280,36,520,720,32,line,14,0xf0,0);
        rect(d,1280,36,556,728,91,0x18);
        rect(d,1280,36,556,728,1,0x50);
        if(voice_timing_current(u)) {
            snprintf(line,sizeof(line),"%s / PS %s / %u",u->voice_timing_reference ? "REFERENCE PCM":"VOICE",app_state_name(u->app.state),
                     (unsigned)u->voice_timing_request);
            text(d,1280,48,562,704,22,line,14,0xe0,0);
            snprintf(line,sizeof(line),"Time %u.%03u ms",(unsigned)(u->voice_total_us/1000U),
                     (unsigned)(u->voice_total_us%1000U));
            text(d,1280,48,589,704,27,line,20,0xf0,0);
            if(u->voice_frontend_us || u->voice_cnn_us)
                snprintf(line,sizeof(line),"Frontend %u.%03u ms   CNN %u.%03u ms",
                         (unsigned)(u->voice_frontend_us/1000U),(unsigned)(u->voice_frontend_us%1000U),
                         (unsigned)(u->voice_cnn_us/1000U),(unsigned)(u->voice_cnn_us%1000U));
            else snprintf(line,sizeof(line),"Frontend -- ms   CNN -- ms  (skipped)");
        } else {
            text(d,1280,48,562,704,22,"VOICE / PS RECOGNITION",14,0xe0,0);
            text(d,1280,48,589,704,27,"Time -- ms",20,0xf0,0);
            snprintf(line,sizeof(line),"Frontend -- ms   CNN -- ms");
        }
        text(d,1280,48,621,704,22,line,14,0xc8,0);
        text(d,1280,36,652,728,22,"Time: process CPU; excludes recording and waiting.",14,0xb0,0);
        text(d,1280,36,680,728,22,u->app.recognizer_ready ?
             "PC: start once; keep quiet 0.5s, then speak":"ASR model pending / recognition unavailable",14,0xcc,0);
    } else if(u->preprocess_active) {
        unsigned x,y;
        const PrepReport *q=&u->preprocess_report;
        text(d,1280,36,517,136,22,"Input 64 x 64",14,0xd0,0);
        rect(d,1280,36,546,128,128,0);
        for(y=0;y<128;++y) for(x=0;x<128;++x)
            pixel(d,1280,36+x,546+y,u->preprocess_input[(y/2U)*64U+x/2U]);
        snprintf(line,sizeof(line),"%s %s %s / %u",u->result_source==UI_SOURCE_CAMERA ? "CAMERA":"PREPROCESS","PL+PS",
            u->result_source==UI_SOURCE_CAMERA ? (u->status==UI_CAPTURE ? "CAPTURE":camera_state_name(u->camera_state)):
            u->preprocess_sequence ? prep_code_name((PrepCode)q->code):"WAIT",u->preprocess_sequence);
        text(d,1280,184,520,572,27,line,20,0xe0,0);
        if(u->result_source==UI_SOURCE_CAMERA) {
            snprintf(line,sizeof(line),"Prep %s  CNN seq %u  code %d",prep_code_name((PrepCode)q->code),
                (unsigned)u->camera_inference.transfer.sequence,u->camera_inference.status);
            text(d,1280,184,553,572,22,line,14,0xb0,0);
            snprintf(line,sizeof(line),"Time %u.%03u ms  FC %u us",(unsigned)(u->camera_total_us/1000U),
                (unsigned)(u->camera_total_us%1000U),(unsigned)u->camera_inference.fc_us);
        } else snprintf(line,sizeof(line),"Prep %u.%03u ms  threshold %u  kept %u",(unsigned)(q->total_us/1000U),
            (unsigned)(q->total_us%1000U),(unsigned)q->threshold,(unsigned)q->kept);
        text(d,1280,184,580,572,23,line,14,0xc8,0);
        snprintf(line,sizeof(line),"Preview %u.%u fps  DMA %08lX / %08lX",u->fps_x10/10U,u->fps_x10%10U,(unsigned long)u->read_errors,(unsigned long)u->write_errors);
        text(d,1280,184,607,572,23,line,14,0xb0,0);
        text(d,1280,184,637,572,22,"app.recognize() / app.preprocess()",14,0xd0,0);
        text(d,1280,184,665,572,22,"Keep dark strokes inside the yellow dashed guide.",14,0xa8,0);
    } else {
    status_y=520;
    snprintf(line,sizeof(line),"%s：%s",u->demo_status ? "状态演示":"识别状态",status_text[u->status]);
    text(d,1280,36,status_y,720,27,line,20,0xe0,0);
    text(d,1280,36,552,720,22,"Notebook controls camera preview and recognition.",14,0xb0,0);
    snprintf(line,sizeof(line),"摄像头：%s  预览：%s  预览帧率：%u.%u fps  累计：%u",
       u->sensor_ok ? "已连接":"未检测到",u->bars ? "彩条":"实时",
       u->fps_x10/10U,u->fps_x10%10U,u->frames);
    text(d,1280,36,582,720,23,line,14,0xc8,0);
    snprintf(line,sizeof(line),"DMA读/写错误：%08lX / %08lX  自动演示：%s",
       (unsigned long)u->read_errors,(unsigned long)u->write_errors,u->auto_demo ? "开":"关");
    text(d,1280,36,611,720,23,line,14,0xb0,0);
    text(d,1280,36,643,720,22,"app.recognize()  app.preprocess()  app.status()",14,0xd0,0);
    text(d,1280,36,672,720,22,"app.clear()  app.status()  app.stop()",14,0xa8,0);
    }
    /* Keep padding untouched to avoid writing into another buffer slot. */
    r=u->revision;u->slot_revision[slot]=r;
    return 1;
}
