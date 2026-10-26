#include "app_control.h"
#include <string.h>
#include <stdio.h>
static void next(uint32_t *n) {if(!++*n) ++*n;}
const char *app_mode_name(AppMode m) {return m==APP_VOICE ? "VOICE":"CAMERA";}
const char *app_source_name(AppSource s) {
    static const char *names[]={"NONE","CAMERA","VOICE","TEST","GOLDEN","DEMO","EXTERNAL"};
    return (unsigned)s<7 ? names[s]:"NONE";
}
const char *app_state_name(AppState s) {
    static const char *names[]={"IDLE","ARMED","LISTENING","PROCESSING","RESULT","REJECTED","ERROR"};
    return (unsigned)s<7 ? names[s]:"ERROR";
}
void app_init(AppControl *a) {
    memset(a,0,sizeof(*a));a->mode_epoch=1;a->selection_seq=1;
    a->class_id=CHEM_COUNT;a->reason="WAIT";
}
void app_clear_selection(AppControl *a,const char *reason) {
    a->valid=0;a->class_id=CHEM_COUNT;a->source=APP_NONE;
    a->reason=reason;next(&a->selection_seq);
}
void app_cancel(AppControl *a) {
    next(&a->mode_epoch);a->active=0;a->auto_voice=0;a->state=APP_IDLE;
    app_clear_selection(a,"CANCELLED");
}
int app_set_mode(AppControl *a,AppMode mode) {
    if(mode!=APP_CAMERA && mode!=APP_VOICE) return -1;
    if(a->mode==mode) return 0;
    app_cancel(a);a->mode=mode;a->reason="MODE_CHANGED";return 1;
}
int app_begin(AppControl *a,AppSource source) {
    if((source==APP_SOURCE_CAMERA && a->mode!=APP_CAMERA) ||
       (source==APP_SOURCE_VOICE && a->mode!=APP_VOICE) ||
       (source!=APP_SOURCE_CAMERA && source!=APP_SOURCE_VOICE)) return -1;
    if(a->active) return -2;
    if(source==APP_SOURCE_VOICE && (!a->audio_ready || !a->recognizer_ready)) {
        a->state=APP_ERROR;
        app_clear_selection(a,!a->audio_ready ? "AUDIO_NOT_READY":"MODEL_NOT_READY");return -3;
    }
    next(&a->request_id);a->request_epoch=a->mode_epoch;a->active=1;
    a->state=APP_ARMED;app_clear_selection(a,"REQUEST_STARTED");return 0;
}
int app_begin_capture(AppControl *a) {
    if(a->mode!=APP_VOICE) return -1;
    if(a->active) return -2;
    if(!a->audio_ready) {a->state=APP_ERROR;app_clear_selection(a,"AUDIO_NOT_READY");return -3;}
    next(&a->request_id);a->request_epoch=a->mode_epoch;a->active=1;a->state=APP_ARMED;
    app_clear_selection(a,"CAPTURE_ONLY");return 0;
}
int app_publish(AppControl *a,AppSource source,unsigned id,uint32_t epoch,uint32_t request) {
    if(source==APP_SOURCE_VOICE && !a->recognizer_ready) return -1;
    if(id>=CHEM_COUNT || !a->active || epoch!=a->mode_epoch ||
       epoch!=a->request_epoch || request!=a->request_id) return -1;
    if((source==APP_SOURCE_CAMERA && a->mode!=APP_CAMERA) ||
       (source==APP_SOURCE_VOICE && a->mode!=APP_VOICE) ||
       (source!=APP_SOURCE_CAMERA && source!=APP_SOURCE_VOICE)) return -1;
    a->class_id=id;a->valid=1;a->source=source;a->active=0;
    a->state=APP_RESULT;a->reason="OK";next(&a->selection_seq);return 0;
}
int app_reference(AppControl *a,AppSource source,unsigned id) {
    if(id>=CHEM_COUNT || (source!=APP_TEST && source!=APP_EXTERNAL && source!=APP_GOLDEN && source!=APP_DEMO)) return -1;
    if(source!=APP_TEST && source!=APP_EXTERNAL && a->mode!=APP_CAMERA) return -1;
    next(&a->mode_epoch);next(&a->request_id);a->active=0;a->auto_voice=0;
    a->class_id=id;a->valid=1;a->source=source;a->state=APP_RESULT;
    a->reason=source==APP_TEST ? "TEST_INJECTION":source==APP_EXTERNAL ? "EXTERNAL_ID_INPUT":"REFERENCE";
    next(&a->selection_seq);return 0;
}
int app_command_feed(AppCommandStream *s,unsigned char c) {
    if(!s->active) {
        if(c!=':') return 0;
        s->active=1;s->length=0;s->overflow=0;
    }
    if(c==27) {s->active=0;s->length=0;s->overflow=0;return -2;}
    if(c=='\r' || c=='\n') {
        s->active=0;s->line[s->length]=0;return s->overflow ? -1:2;
    }
    if(s->length<96 && !s->overflow) s->line[s->length++]=(char)c;
    else s->overflow=1;
    return 1;
}
AppCommand app_command_parse(const char *s,unsigned *id) {
    static const char *names[]={":mode camera",":mode voice",":voice once",":voice auto on",
        ":voice auto off",":cancel",":status",":audio mic",":audio linein"};
    unsigned i,value=0,digits=0;
    for(i=0;i<9;++i) if(!strcmp(s,names[i])) return (AppCommand)(CMD_MODE_CAMERA+i);
    if(!strcmp(s,":audio capture")) return CMD_CAPTURE;
    if(!strcmp(s,":audio record")) return CMD_RECORD;
    if(!strcmp(s,":clear")) return CMD_CLEAR;
    if(!strcmp(s,":audio dump")) return CMD_DUMP;
    if(strncmp(s,":test select ",13)) return CMD_INVALID;
    for(s+=13;*s;++s) {
        if(*s<'0' || *s>'9' || ++digits>2) return CMD_INVALID;
        value=value*10U+(unsigned)(*s-'0');
    }
    if(!digits || value>=CHEM_COUNT) return CMD_INVALID;
    *id=value;return CMD_TEST_SELECT;
}
int app_selection_json(const AppControl *a,char *d,size_t n) {
    int used;
    if(a->valid && a->class_id<CHEM_COUNT) {
        const Chemical *c=&chemicals[a->class_id];
        used=snprintf(d,n,"@EVT {\"v\":1,\"type\":\"selection\",\"mode\":\"%s\",\"mode_epoch\":%lu,\"request_id\":%lu,\"selection_seq\":%lu,\"source\":\"%s\",\"backend\":\"%s\",\"valid\":true,\"class_id\":%u,\"label\":\"%s\",\"name\":\"%s\",\"formula\":\"%s\",\"model_key\":\"%s\",\"score\":null,\"reason\":\"%s\"}\r\n",
            app_mode_name(a->mode),(unsigned long)a->mode_epoch,(unsigned long)a->request_id,
            (unsigned long)a->selection_seq,app_source_name(a->source),a->source==APP_TEST ? "TEST":a->source==APP_EXTERNAL ? "EXTERNAL":"BOARD",
            a->class_id,c->label,c->zh,c->formula,c->model,a->reason);
    } else used=snprintf(d,n,"@EVT {\"v\":1,\"type\":\"selection\",\"mode\":\"%s\",\"mode_epoch\":%lu,\"request_id\":%lu,\"selection_seq\":%lu,\"valid\":false,\"class_id\":null,\"label\":null,\"model_key\":null,\"reason\":\"%s\"}\r\n",
        app_mode_name(a->mode),(unsigned long)a->mode_epoch,(unsigned long)a->request_id,(unsigned long)a->selection_seq,a->reason);
    return used<0 || (size_t)used>=n ? -1:used;
}
int app_state_json(const AppControl *a,char *d,size_t n) {
    int used=snprintf(d,n,"@EVT {\"v\":1,\"type\":\"state\",\"mode\":\"%s\",\"state\":\"%s\",\"trigger\":\"%s\",\"audio_input\":\"%s\",\"audio_ready\":%s,\"recognizer_ready\":%s,\"reason\":\"%s\",\"mode_epoch\":%lu,\"request_id\":%lu,\"active\":%s}\r\n",
        app_mode_name(a->mode),app_state_name(a->state),a->auto_voice ? "AUTO":"ONCE",
        a->line_input ? "LINE_IN":"ONBOARD_MIC",a->audio_ready ? "true":"false",
        a->recognizer_ready ? "true":"false",a->reason,(unsigned long)a->mode_epoch,
        (unsigned long)a->request_id,a->active ? "true":"false");
    return used<0 || (size_t)used>=n ? -1:used;
}
