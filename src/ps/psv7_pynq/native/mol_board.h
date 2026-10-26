#ifndef MOL_BOARD_H
#define MOL_BOARD_H
#include "ui_panel.h"
#include "mol_render.h"
#define MOL_BOARD_WIDTH 256U
#define MOL_BOARD_HEIGHT 256U
#define MOL_BOARD_X 904U
#define MOL_BOARD_Y 420U
#define MOL_BOARD_TARGET_FPS 15U
#define MOL_BOARD_SPEED_DEG 36.0f
typedef struct {
    unsigned renders, presents, class_id, active, paused;
    unsigned render_us_last, render_us_max, render_errors;
    float angle;
} MolBoardStats;
int mol_board_init(void);
/* Shared current selection; an invalid result clears the displayed model. */
int mol_board_update(const UiPanel *ui, uint64_t ticks, uint64_t frequency);
int mol_board_composite(uint8_t *frame,size_t bytes,const PreviewLayout *layout);
void mol_board_pause_toggle(void);
void mol_board_reset(void);
void mol_board_presented(void);
void mol_board_render_time(unsigned us);
const MolBoardStats *mol_board_stats(void);
#endif
