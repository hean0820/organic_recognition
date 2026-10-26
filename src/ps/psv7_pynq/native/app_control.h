#ifndef APP_CONTROL_H
#define APP_CONTROL_H
#include <stdint.h>
#include <stddef.h>
#include "chem_db.h"
typedef enum {APP_CAMERA, APP_VOICE} AppMode;
typedef enum {APP_NONE,APP_SOURCE_CAMERA,APP_SOURCE_VOICE,APP_TEST,APP_GOLDEN,APP_DEMO,APP_EXTERNAL} AppSource;
typedef enum {APP_IDLE,APP_ARMED,APP_LISTENING,APP_PROCESSING,APP_RESULT,APP_REJECTED,APP_ERROR} AppState;
typedef struct {
    AppMode mode;
    AppState state;
    AppSource source;
    uint32_t mode_epoch,request_id,request_epoch,selection_seq;
    unsigned class_id;
    int valid,active,audio_ready,recognizer_ready,auto_voice,line_input;
    const char *reason;
} AppControl;
typedef struct {char line[97];unsigned length;int active,overflow;} AppCommandStream;
typedef enum {CMD_INVALID,CMD_MODE_CAMERA,CMD_MODE_VOICE,CMD_ONCE,CMD_AUTO_ON,
    CMD_AUTO_OFF,CMD_CANCEL,CMD_STATUS,CMD_AUDIO_MIC,CMD_AUDIO_LINE,CMD_TEST_SELECT,CMD_CAPTURE,CMD_DUMP,CMD_RECORD,CMD_CLEAR} AppCommand;
void app_init(AppControl *a);
int app_set_mode(AppControl *a,AppMode mode);
void app_clear_selection(AppControl *a,const char *reason);
void app_cancel(AppControl *a);
int app_begin(AppControl *a,AppSource source);
int app_begin_capture(AppControl *a);
int app_publish(AppControl *a,AppSource source,unsigned id,uint32_t epoch,uint32_t request);
int app_reference(AppControl *a,AppSource source,unsigned id);
const char *app_mode_name(AppMode mode);
const char *app_source_name(AppSource source);
const char *app_state_name(AppState state);
/* 0=legacy byte, 1=consumed, 2=complete line, -1=overflow, -2=escape. */
int app_command_feed(AppCommandStream *s,unsigned char c);
AppCommand app_command_parse(const char *line,unsigned *id);
int app_selection_json(const AppControl *a,char *dst,size_t size);
int app_state_json(const AppControl *a,char *dst,size_t size);
#endif
