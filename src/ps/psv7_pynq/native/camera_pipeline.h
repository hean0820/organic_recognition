#ifndef CAMERA_PIPELINE_H
#define CAMERA_PIPELINE_H
#include "cnn_inference.h"
typedef enum {
    CAMERA_WAIT, CAMERA_INPUT_READY, CAMERA_REJECTED, CAMERA_INFER_FAILED,
    CAMERA_RESULT, CAMERA_CAPTURE_FAILED
} CameraState;
typedef struct {
    PrepWorkspace work;
    uint8_t input[CNN_INPUT_BYTES], features[CNN_FEATURE_BYTES];
    PrepReport prep;
    CnnInference inference;
    unsigned capture_sequence;
    int captured, classify;
    CameraState state;
    uint32_t total_us;
} CameraPipeline;
/* Reset public snapshots while keeping monotonically increasing capture sequence. */
void camera_pipeline_clear(CameraPipeline *camera);
const char *camera_state_name(CameraState state);
CameraState camera_pipeline_capture_backend(CameraPipeline *camera,const uint8_t *frame,
                  size_t bytes,size_t stride,int classify,const CnnIo *io,
                  const CnnParameters *parameters,const PrepClock *clock,const PrepBackend *backend);
#endif
