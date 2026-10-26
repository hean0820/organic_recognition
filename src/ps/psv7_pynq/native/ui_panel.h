#ifndef UI_PANEL_H
#define UI_PANEL_H
#include <stddef.h>
#include <stdint.h>
#include "preview_compose.h"
#include "chem_db.h"
#include "preprocess.h"
#include "camera_pipeline.h"
#include "app_control.h"

typedef enum {
    UI_WAIT, UI_CAPTURE, UI_PROCESS, UI_INFER, UI_DONE, UI_BLANK, UI_ERROR,
    UI_STATUS_COUNT
} UiStatus;
typedef enum {
    UI_SOURCE_WAIT, UI_SOURCE_DEMO, UI_SOURCE_GOLDEN, UI_SOURCE_CAMERA, UI_SOURCE_PREPROCESS,
    UI_SOURCE_VOICE, UI_SOURCE_TEST, UI_SOURCE_EXTERNAL
} UiResultSource;
typedef struct {
    AppControl app;
    uint32_t revision;
    uint32_t slot_revision[3];
    unsigned class_id, sequence, fps_x10, frames;
    uint32_t read_errors, write_errors;
    UiStatus status;
    int demo_class, demo_status, auto_demo, sensor_ok, bars;
    int preprocess_active;
    unsigned preprocess_sequence;
    PrepReport preprocess_report;
    uint8_t preprocess_input[4096];
    UiResultSource result_source;
    CameraState camera_state;
    CnnInference camera_inference;
    uint32_t camera_total_us;
    int camera_valid;
    unsigned audio_level,audio_noise,audio_samples,audio_dropped;
    uint32_t voice_total_us,voice_frontend_us,voice_cnn_us;
    uint32_t voice_timing_epoch,voice_timing_request,voice_timing_selection_seq;
    int voice_timing_valid,voice_timing_reference;
} UiPanel;

void ui_init(UiPanel *ui);
int ui_demo_class(UiPanel *ui, unsigned id);
int ui_result(UiPanel *ui, unsigned id, unsigned sequence);
int ui_status(UiPanel *ui, UiStatus status, int demo);
void ui_auto(UiPanel *ui, int enabled);
void ui_stats(UiPanel *ui, int sensor_ok, int bars, unsigned fps_x10,
              unsigned frames, uint32_t read_errors, uint32_t write_errors);
void ui_invalidate(UiPanel *ui);
/* Returns 1 when updated, 0 when unchanged, -1 on invalid input. */
int ui_render(UiPanel *ui, unsigned slot, uint8_t *dst, size_t bytes,
              const PreviewLayout *layout);
unsigned ui_missing_glyphs(void);
void ui_preprocess_result(UiPanel *ui,const uint8_t *input,const PrepReport *report,unsigned sequence);
void ui_camera_begin(UiPanel *ui);
void ui_golden_begin(UiPanel *ui);
void ui_camera_snapshot(UiPanel *ui,const CameraPipeline *camera);
void ui_mode(UiPanel *ui,AppMode mode);
void ui_app_refresh(UiPanel *ui);
/* Compute time only, published after the matching recognition result. */
int ui_voice_timing(UiPanel *ui,uint32_t epoch,uint32_t request,
                    uint32_t total_us,uint32_t frontend_us,uint32_t cnn_us);
int ui_test_select(UiPanel *ui,unsigned id);
int ui_voice_class(UiPanel *ui,unsigned id);
#endif
