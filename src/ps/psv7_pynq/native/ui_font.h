#ifndef UI_FONT_H
#define UI_FONT_H
#include <stdint.h>
typedef struct {
    uint32_t codepoint;
    uint8_t size, width, height, advance;
    uint32_t offset;
} UiGlyph;
extern const UiGlyph ui_glyphs[];
extern const unsigned ui_glyph_count;
extern const uint8_t ui_font_bits[];
#endif
