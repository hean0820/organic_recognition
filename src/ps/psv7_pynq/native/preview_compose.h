#ifndef PREVIEW_COMPOSE_H
#define PREVIEW_COMPOSE_H
#include <stdint.h>
#include <stddef.h>

typedef struct {
    unsigned width, height;
    unsigned camera_x, camera_y, camera_width, camera_height;
} PreviewLayout;

PreviewLayout preview_layout(int mode_1080);
int preview_compose(uint8_t *display, size_t display_bytes,
                    const uint8_t *camera, size_t camera_bytes,
                    const PreviewLayout *layout);
void preview_background(uint8_t *display, const PreviewLayout *layout);
void preview_pattern(uint8_t *display, const PreviewLayout *layout);
void preview_camera_roi(uint8_t *display, const PreviewLayout *layout);
void prep_preview_guide(uint8_t *display,const PreviewLayout *layout);
#endif
