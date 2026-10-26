#include "voice_recognizer.h"
#include "voice_model_selftest.h"
#include <math.h>
#include <string.h>
static int ready;
static int16_t probe[640];
static float features[CHEM22_FEATURES],outputs[24];
int voice_recognizer_init(void) {
    unsigned i;
    Chem22Result result;
    ready=0;
    if(CHEM_COUNT!=CHEM22_CLASS_COUNT ||
       strcmp(chem22_model_version(),VOICE_EXPECTED_VERSION)) return -1;
    /* Fixed, non-speech input checks the actual frontend and all CNN layers. */
    for(i=0;i<640;++i) probe[i]=(int16_t)(((int)(i%32U)-16)*300);
    if(chem22_frontend(probe,640,features)) return -1;
    chem22_logits(features,outputs);
    for(i=0;i<24;++i)
        if(!isfinite(outputs[i]) || fabsf(outputs[i]-voice_expected_logits[i])>.02f) return -1;
    memset(probe,0,sizeof(probe));
    if(chem22_predict_pcm(probe,640,&result) || result.class_id!=-1 || result.reason!=2) return -1;
    ready=1;return 0;
}
int voice_recognizer_predict(const int16_t *pcm,size_t count,Chem22Result *r) {
    if(!ready) {
        if(r) {memset(r,0,sizeof(*r));r->class_id=-1;r->raw_class=-1;r->reason=3;}
        return -1;
    }
    return chem22_predict_pcm(pcm,count,r);
}
const char *voice_recognizer_reason(const Chem22Result *r) {
    if(!r || r->reason==3 || !isfinite(r->confidence) || !isfinite(r->margin) ||
       r->confidence<0 || r->confidence>1 || r->margin<0 || r->margin>1 ||
       (r->reason==0 && (r->class_id<0 || r->class_id>=CHEM22_CLASS_COUNT))) return "MODEL_ERROR";
    if(r->reason==2) return "SILENCE";
    if(r->reason!=0 || r->class_id<0 || r->class_id>=CHEM22_CLASS_COUNT) return "UNKNOWN_OR_LOW_SCORE";
    return "OK";
}
int voice_recognizer_apply(UiPanel *u,const Chem22Result *r,uint32_t epoch,uint32_t request) {
    if(!u || !r || !ready || !u->app.recognizer_ready || !u->app.active ||
       u->app.mode!=APP_VOICE || epoch!=u->app.mode_epoch ||
       epoch!=u->app.request_epoch || request!=u->app.request_id) return -1;
    if(!strcmp(voice_recognizer_reason(r),"OK")) {
        if(app_publish(&u->app,APP_SOURCE_VOICE,(unsigned)r->class_id,epoch,request)) return -1;
        ui_app_refresh(u);return 0;
    }
    u->app.active=0;
    u->app.state=!strcmp(voice_recognizer_reason(r),"MODEL_ERROR") ? APP_ERROR:APP_REJECTED;
    app_clear_selection(&u->app,voice_recognizer_reason(r));
    ui_app_refresh(u);return 1;
}
