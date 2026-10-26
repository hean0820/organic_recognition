#ifndef MOL_RENDER_H
#define MOL_RENDER_H
#include "molecule_models.h"
#define MOL_RENDER_MAX_ATOMS 64U
#define MOL_RENDER_MAX_BONDS 128U
typedef struct {
    uint8_t *color;
    float *depth;
    unsigned width, height, stride;
    size_t color_bytes, depth_count;
} MolSurface;
/* BGR888; stride is BYTES. Depth is tightly packed float, larger z is nearer.
   Caller owns/reuses buffers. No heap, DMA, cache or display ownership here. */
int mol_surface_init(MolSurface *s, uint8_t *color, size_t bytes, float *depth,
                     size_t count, unsigned w, unsigned h, unsigned stride);
void mol_surface_clear(MolSurface *s);
/* Always transforms original coordinates; NULL clears. Invalid data clears,
   returns -1. Rotation is degrees, orthographic view, y points upward. */
int mol_render(MolSurface *s, const Mol3DModel *model, float tilt, float angle);
/* Checked region copy; frame stride also BYTES. Never writes outside region. */
int mol_blit(const MolSurface *s, uint8_t *frame, size_t bytes,
             unsigned fw, unsigned fh, unsigned stride, unsigned x, unsigned y);
#endif
