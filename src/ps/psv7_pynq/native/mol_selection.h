#ifndef MOL_SELECTION_H
#define MOL_SELECTION_H
#include "ui_panel.h"
#define MOL_MAPPING_VERSION "result_9_molecule3d_v2"
#define MOL_EVENT_PREFIX "MOL3D_EVT "
#define MOL_UART_BAUD 115200U
typedef enum {MOL_SOURCE_MANUAL,MOL_SOURCE_CNN,MOL_SOURCE_GOLDEN,MOL_SOURCE_VOICE} MolSource;
typedef struct {int class_id;MolSource source;unsigned pending,revision,result_sequence;} MolSelection;
void molecule_selection_init(void);
int molecule_select(MolSource source,unsigned class_id,unsigned sequence);
void molecule_clear(MolSource source);
/* Main loop only: display only the current valid AppControl result;
   pending, rejected, cancelled and mode-changed requests clear the model. */
void molecule_sync(const UiPanel *ui);
const MolSelection *molecule_selection(void);
/* Session token is established by a PC handshake; snapshot on every handshake. */
void molecule_session(unsigned token);
int molecule_event(char *out,size_t bytes,int force_snapshot);
#endif
