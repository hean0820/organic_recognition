#include "mol_selection.h"
#include "molecule_models.h"
#include <string.h>
#include <stdio.h>
static MolSelection state;
static unsigned session,event_seq,emitted_revision;
static const char *source_name[] = {"manual","cnn","golden","voice"};
static void update(int id,MolSource source,unsigned pending,unsigned sequence)
{
    if(state.class_id!=id || state.source!=source || state.pending!=pending || state.result_sequence!=sequence) {
        state.class_id=id;state.source=source;state.pending=pending;state.result_sequence=sequence;
        ++state.revision;if(!state.revision) ++state.revision;
    }
}
void molecule_selection_init(void)
{
    memset(&state,0,sizeof(state));state.class_id=-1;state.revision=1;
    session=event_seq=emitted_revision=0;
}
int molecule_select(MolSource source,unsigned id,unsigned sequence)
{
    if((unsigned)source>MOL_SOURCE_VOICE || id>=MOL3D_CLASS_COUNT || !mol3d_model_by_class(id)) {
        molecule_clear((unsigned)source<=MOL_SOURCE_VOICE ? source:MOL_SOURCE_MANUAL);return -1;
    }
    update((int)id,source,0,sequence);return 0;
}
void molecule_clear(MolSource source) {update(-1,(unsigned)source<=MOL_SOURCE_VOICE ? source:MOL_SOURCE_MANUAL,0,0);}
void molecule_sync(const UiPanel *u)
{
    MolSource source;
    if(!u) {molecule_clear(MOL_SOURCE_MANUAL);return;}
    source=u->app.source==APP_SOURCE_CAMERA ? MOL_SOURCE_CNN:
           u->app.source==APP_GOLDEN ? MOL_SOURCE_GOLDEN:
           (u->app.source==APP_SOURCE_VOICE || u->app.source==APP_EXTERNAL) ?
           MOL_SOURCE_VOICE:MOL_SOURCE_MANUAL;
    /* HDMI information and 3D obey the same current result as the LAN host.
       A new request, rejection, error, cancellation or mode change cannot
       keep a historical molecule after AppControl has invalidated it. */
    if(!u->app.valid || u->app.active || u->app.state!=APP_RESULT ||
       u->app.class_id>=MOL3D_CLASS_COUNT || u->app.source==APP_NONE ||
       (u->app.source==APP_SOURCE_VOICE &&
        (u->app.mode!=APP_VOICE || !u->app.recognizer_ready)) ||
       (u->app.source==APP_SOURCE_CAMERA && u->app.mode!=APP_CAMERA)) {
        molecule_clear(source);return;
    }
    (void)molecule_select(source,u->app.class_id,u->app.selection_seq);
}
const MolSelection *molecule_selection(void) {return &state;}
void molecule_session(unsigned token) {session=token;event_seq=0;emitted_revision=0;}
int molecule_event(char *out,size_t bytes,int force)
{
    const Mol3DModel *m;
    int n;
    if(!out || !bytes || !session || (!force && emitted_revision==state.revision)) return 0;
    m=state.class_id<0 ? 0:mol3d_model_by_class((unsigned)state.class_id);
    /* 32-bit event counter rollover starts a new explicit handshake. */
    if(event_seq==0xffffffffU) {session=0;return 0;}
    n=snprintf(out,bytes,MOL_EVENT_PREFIX
        "{\"protocol_version\":1,\"mapping_version\":\"" MOL_MAPPING_VERSION
        "\",\"session_id\":%u,\"event_seq\":%u,\"source\":\"%s\",\"action\":\"%s\","
        "\"class_id\":%d,\"molecule_id\":\"%s\",\"pending\":%s,\"snapshot\":%s}\r\n",
        session,event_seq+1U,source_name[state.source],m ? "select":"clear",state.class_id,
        m ? m->molecule_id:"",state.pending ? "true":"false",force ? "true":"false");
    if(n<0 || (size_t)n>=bytes) return -1;
    ++event_seq;emitted_revision=state.revision;return n;
}
