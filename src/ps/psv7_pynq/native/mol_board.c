#include "mol_board.h"
#include "mol_selection.h"
#include <math.h>
#include <string.h>
static uint8_t pixels[MOL_BOARD_WIDTH*MOL_BOARD_HEIGHT*3U] __attribute__((aligned(64)));
static float depth[MOL_BOARD_WIDTH*MOL_BOARD_HEIGHT] __attribute__((aligned(64)));
static MolSurface surface;
static MolBoardStats stats;
static const Mol3DModel *model;
static uint64_t last_tick,render_tick;
static unsigned dirty,version,shown_version,reset_pending;
static int selected;
int mol_board_init(void)
{
    memset(&stats,0,sizeof(stats));model=0;selected=-2;
    molecule_selection_init();
    dirty=1;version=shown_version=reset_pending=0;last_tick=render_tick=0;
    return mol_surface_init(&surface,pixels,sizeof(pixels),depth,
        MOL_BOARD_WIDTH*MOL_BOARD_HEIGHT,MOL_BOARD_WIDTH,MOL_BOARD_HEIGHT,MOL_BOARD_WIDTH*3U);
}
int mol_board_update(const UiPanel *ui,uint64_t ticks,uint64_t frequency)
{
    int id;int ret;
    if(!ui || !frequency) return -1;
    molecule_sync(ui);
    id=molecule_selection()->class_id;
    if(id!=selected) {
        selected=id;model=id<0 ? 0:mol3d_model_by_class((unsigned)id);
        stats.class_id=id<0 ? MOL3D_CLASS_COUNT:(unsigned)id;
        stats.active=model!=0;stats.angle=0;dirty=1;last_tick=ticks;
    }
    if(ticks>=last_tick && model && !stats.paused && !reset_pending)
        stats.angle=fmodf(stats.angle+(float)((double)(ticks-last_tick)/frequency)*MOL_BOARD_SPEED_DEG,360);
    last_tick=ticks;reset_pending=0;
    if(!dirty && (!model || stats.paused || ticks-render_tick<frequency/MOL_BOARD_TARGET_FPS)) return 0;
    ret=mol_render(&surface,model,18,stats.angle);
    if(ret<0) {stats.active=0;++stats.render_errors;model=0;}
    ++stats.renders;++version;dirty=0;render_tick=ticks;
    return 1;
}
int mol_board_composite(uint8_t *frame,size_t bytes,const PreviewLayout *p)
{
    if(!p || p->width!=1280 || p->height!=720) return -1;
    /* The UI supplies waiting/pending text when there is no current model. */
    if(!stats.active) return 0;
    return mol_blit(&surface,frame,bytes,p->width,p->height,p->width*3U,MOL_BOARD_X,MOL_BOARD_Y);
}
void mol_board_pause_toggle(void) {stats.paused=!stats.paused;}
void mol_board_reset(void) {stats.angle=0;dirty=reset_pending=1;}
void mol_board_presented(void)
{
    if(stats.active && shown_version!=version) {++stats.presents;shown_version=version;}
}
void mol_board_render_time(unsigned us)
{
    stats.render_us_last=us;
    if(us>stats.render_us_max) stats.render_us_max=us;
}
const MolBoardStats *mol_board_stats(void) {return &stats;}
