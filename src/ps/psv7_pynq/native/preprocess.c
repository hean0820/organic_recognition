#include "preprocess.h"
#include <string.h>

static uint32_t now(const PrepClock *clock)
{return clock && clock->now_us ? clock->now_us(clock->context):0U;}
static uint32_t elapsed(const PrepClock *clock,uint32_t start)
{return now(clock)-start;}
static unsigned round_even(unsigned numerator,unsigned denominator)
{
    unsigned q=numerator/denominator,r=numerator%denominator;
    return q+(r*2U>denominator || (r*2U==denominator && (q&1U)));
}
/* IEEE reflected CRC32: same polynomial, initial value and final complement
 * as the accepted 0.7.0 bit-at-a-time implementation preserved in assets. */
static const uint32_t crc32_table[256]={
    UINT32_C(0x00000000),UINT32_C(0x77073096),UINT32_C(0xee0e612c),UINT32_C(0x990951ba),UINT32_C(0x076dc419),UINT32_C(0x706af48f),UINT32_C(0xe963a535),UINT32_C(0x9e6495a3),
    UINT32_C(0x0edb8832),UINT32_C(0x79dcb8a4),UINT32_C(0xe0d5e91e),UINT32_C(0x97d2d988),UINT32_C(0x09b64c2b),UINT32_C(0x7eb17cbd),UINT32_C(0xe7b82d07),UINT32_C(0x90bf1d91),
    UINT32_C(0x1db71064),UINT32_C(0x6ab020f2),UINT32_C(0xf3b97148),UINT32_C(0x84be41de),UINT32_C(0x1adad47d),UINT32_C(0x6ddde4eb),UINT32_C(0xf4d4b551),UINT32_C(0x83d385c7),
    UINT32_C(0x136c9856),UINT32_C(0x646ba8c0),UINT32_C(0xfd62f97a),UINT32_C(0x8a65c9ec),UINT32_C(0x14015c4f),UINT32_C(0x63066cd9),UINT32_C(0xfa0f3d63),UINT32_C(0x8d080df5),
    UINT32_C(0x3b6e20c8),UINT32_C(0x4c69105e),UINT32_C(0xd56041e4),UINT32_C(0xa2677172),UINT32_C(0x3c03e4d1),UINT32_C(0x4b04d447),UINT32_C(0xd20d85fd),UINT32_C(0xa50ab56b),
    UINT32_C(0x35b5a8fa),UINT32_C(0x42b2986c),UINT32_C(0xdbbbc9d6),UINT32_C(0xacbcf940),UINT32_C(0x32d86ce3),UINT32_C(0x45df5c75),UINT32_C(0xdcd60dcf),UINT32_C(0xabd13d59),
    UINT32_C(0x26d930ac),UINT32_C(0x51de003a),UINT32_C(0xc8d75180),UINT32_C(0xbfd06116),UINT32_C(0x21b4f4b5),UINT32_C(0x56b3c423),UINT32_C(0xcfba9599),UINT32_C(0xb8bda50f),
    UINT32_C(0x2802b89e),UINT32_C(0x5f058808),UINT32_C(0xc60cd9b2),UINT32_C(0xb10be924),UINT32_C(0x2f6f7c87),UINT32_C(0x58684c11),UINT32_C(0xc1611dab),UINT32_C(0xb6662d3d),
    UINT32_C(0x76dc4190),UINT32_C(0x01db7106),UINT32_C(0x98d220bc),UINT32_C(0xefd5102a),UINT32_C(0x71b18589),UINT32_C(0x06b6b51f),UINT32_C(0x9fbfe4a5),UINT32_C(0xe8b8d433),
    UINT32_C(0x7807c9a2),UINT32_C(0x0f00f934),UINT32_C(0x9609a88e),UINT32_C(0xe10e9818),UINT32_C(0x7f6a0dbb),UINT32_C(0x086d3d2d),UINT32_C(0x91646c97),UINT32_C(0xe6635c01),
    UINT32_C(0x6b6b51f4),UINT32_C(0x1c6c6162),UINT32_C(0x856530d8),UINT32_C(0xf262004e),UINT32_C(0x6c0695ed),UINT32_C(0x1b01a57b),UINT32_C(0x8208f4c1),UINT32_C(0xf50fc457),
    UINT32_C(0x65b0d9c6),UINT32_C(0x12b7e950),UINT32_C(0x8bbeb8ea),UINT32_C(0xfcb9887c),UINT32_C(0x62dd1ddf),UINT32_C(0x15da2d49),UINT32_C(0x8cd37cf3),UINT32_C(0xfbd44c65),
    UINT32_C(0x4db26158),UINT32_C(0x3ab551ce),UINT32_C(0xa3bc0074),UINT32_C(0xd4bb30e2),UINT32_C(0x4adfa541),UINT32_C(0x3dd895d7),UINT32_C(0xa4d1c46d),UINT32_C(0xd3d6f4fb),
    UINT32_C(0x4369e96a),UINT32_C(0x346ed9fc),UINT32_C(0xad678846),UINT32_C(0xda60b8d0),UINT32_C(0x44042d73),UINT32_C(0x33031de5),UINT32_C(0xaa0a4c5f),UINT32_C(0xdd0d7cc9),
    UINT32_C(0x5005713c),UINT32_C(0x270241aa),UINT32_C(0xbe0b1010),UINT32_C(0xc90c2086),UINT32_C(0x5768b525),UINT32_C(0x206f85b3),UINT32_C(0xb966d409),UINT32_C(0xce61e49f),
    UINT32_C(0x5edef90e),UINT32_C(0x29d9c998),UINT32_C(0xb0d09822),UINT32_C(0xc7d7a8b4),UINT32_C(0x59b33d17),UINT32_C(0x2eb40d81),UINT32_C(0xb7bd5c3b),UINT32_C(0xc0ba6cad),
    UINT32_C(0xedb88320),UINT32_C(0x9abfb3b6),UINT32_C(0x03b6e20c),UINT32_C(0x74b1d29a),UINT32_C(0xead54739),UINT32_C(0x9dd277af),UINT32_C(0x04db2615),UINT32_C(0x73dc1683),
    UINT32_C(0xe3630b12),UINT32_C(0x94643b84),UINT32_C(0x0d6d6a3e),UINT32_C(0x7a6a5aa8),UINT32_C(0xe40ecf0b),UINT32_C(0x9309ff9d),UINT32_C(0x0a00ae27),UINT32_C(0x7d079eb1),
    UINT32_C(0xf00f9344),UINT32_C(0x8708a3d2),UINT32_C(0x1e01f268),UINT32_C(0x6906c2fe),UINT32_C(0xf762575d),UINT32_C(0x806567cb),UINT32_C(0x196c3671),UINT32_C(0x6e6b06e7),
    UINT32_C(0xfed41b76),UINT32_C(0x89d32be0),UINT32_C(0x10da7a5a),UINT32_C(0x67dd4acc),UINT32_C(0xf9b9df6f),UINT32_C(0x8ebeeff9),UINT32_C(0x17b7be43),UINT32_C(0x60b08ed5),
    UINT32_C(0xd6d6a3e8),UINT32_C(0xa1d1937e),UINT32_C(0x38d8c2c4),UINT32_C(0x4fdff252),UINT32_C(0xd1bb67f1),UINT32_C(0xa6bc5767),UINT32_C(0x3fb506dd),UINT32_C(0x48b2364b),
    UINT32_C(0xd80d2bda),UINT32_C(0xaf0a1b4c),UINT32_C(0x36034af6),UINT32_C(0x41047a60),UINT32_C(0xdf60efc3),UINT32_C(0xa867df55),UINT32_C(0x316e8eef),UINT32_C(0x4669be79),
    UINT32_C(0xcb61b38c),UINT32_C(0xbc66831a),UINT32_C(0x256fd2a0),UINT32_C(0x5268e236),UINT32_C(0xcc0c7795),UINT32_C(0xbb0b4703),UINT32_C(0x220216b9),UINT32_C(0x5505262f),
    UINT32_C(0xc5ba3bbe),UINT32_C(0xb2bd0b28),UINT32_C(0x2bb45a92),UINT32_C(0x5cb36a04),UINT32_C(0xc2d7ffa7),UINT32_C(0xb5d0cf31),UINT32_C(0x2cd99e8b),UINT32_C(0x5bdeae1d),
    UINT32_C(0x9b64c2b0),UINT32_C(0xec63f226),UINT32_C(0x756aa39c),UINT32_C(0x026d930a),UINT32_C(0x9c0906a9),UINT32_C(0xeb0e363f),UINT32_C(0x72076785),UINT32_C(0x05005713),
    UINT32_C(0x95bf4a82),UINT32_C(0xe2b87a14),UINT32_C(0x7bb12bae),UINT32_C(0x0cb61b38),UINT32_C(0x92d28e9b),UINT32_C(0xe5d5be0d),UINT32_C(0x7cdcefb7),UINT32_C(0x0bdbdf21),
    UINT32_C(0x86d3d2d4),UINT32_C(0xf1d4e242),UINT32_C(0x68ddb3f8),UINT32_C(0x1fda836e),UINT32_C(0x81be16cd),UINT32_C(0xf6b9265b),UINT32_C(0x6fb077e1),UINT32_C(0x18b74777),
    UINT32_C(0x88085ae6),UINT32_C(0xff0f6a70),UINT32_C(0x66063bca),UINT32_C(0x11010b5c),UINT32_C(0x8f659eff),UINT32_C(0xf862ae69),UINT32_C(0x616bffd3),UINT32_C(0x166ccf45),
    UINT32_C(0xa00ae278),UINT32_C(0xd70dd2ee),UINT32_C(0x4e048354),UINT32_C(0x3903b3c2),UINT32_C(0xa7672661),UINT32_C(0xd06016f7),UINT32_C(0x4969474d),UINT32_C(0x3e6e77db),
    UINT32_C(0xaed16a4a),UINT32_C(0xd9d65adc),UINT32_C(0x40df0b66),UINT32_C(0x37d83bf0),UINT32_C(0xa9bcae53),UINT32_C(0xdebb9ec5),UINT32_C(0x47b2cf7f),UINT32_C(0x30b5ffe9),
    UINT32_C(0xbdbdf21c),UINT32_C(0xcabac28a),UINT32_C(0x53b39330),UINT32_C(0x24b4a3a6),UINT32_C(0xbad03605),UINT32_C(0xcdd70693),UINT32_C(0x54de5729),UINT32_C(0x23d967bf),
    UINT32_C(0xb3667a2e),UINT32_C(0xc4614ab8),UINT32_C(0x5d681b02),UINT32_C(0x2a6f2b94),UINT32_C(0xb40bbe37),UINT32_C(0xc30c8ea1),UINT32_C(0x5a05df1b),UINT32_C(0x2d02ef8d),
};
uint32_t prep_crc32(const uint8_t *p,size_t n)
{
    uint32_t crc=UINT32_C(0xffffffff);size_t i;
    for(i=0;i<n;++i) crc=(crc>>8)^crc32_table[(crc^p[i])&255U];
    return ~crc;
}
const char *prep_code_name(PrepCode code)
{
    static const char *names[]={"OK","BLANK","EDGE","DARK","WEAK","BAD_ARGUMENT","ACCEL_ERROR"};
    return (unsigned)code<sizeof(names)/sizeof(names[0]) ? names[code]:"UNKNOWN";
}

/* Percentile interpolation retained on PS after PL filtering. */
static unsigned quantile_milli(const uint32_t hist[256],unsigned n,unsigned per_mille)
{
    unsigned rank=(n-1U)*per_mille,lo=rank/1000U,hi=(rank+999U)/1000U;
    unsigned cumulative=0,v,lv=0,hv=0;int have=0;
    for(v=0;v<256;++v) {
        cumulative+=hist[v];
        if(!have && cumulative>lo) {lv=v;have=1;}
        if(cumulative>hi) {hv=v;break;}
    }
    return lv*1000U+(hv-lv)*(rank%1000U);
}
static PrepCode components(PrepWorkspace *w,PrepReport *r)
{
    uint32_t hist[256]={0};unsigned i,x,y,x0=PREP_WORK_W,y0=PREP_WORK_H,x1=0,y1=0;
    unsigned total_gray=0;
    for(i=0;i<PREP_WORK_N;++i) {++hist[w->ink[i]];total_gray+=w->gray[i];}
    r->mean_gray=total_gray/PREP_WORK_N;
    r->threshold=quantile_milli(hist,PREP_WORK_N,985U)/1000U;
    if(r->threshold<8U) r->threshold=8U;
    memset(w->visited,0,sizeof(w->visited));
    for(i=0;i<PREP_WORK_N;++i) if(!w->visited[i] && w->ink[i]>=r->threshold) {
        unsigned head=0,tail=1,cx0=PREP_WORK_W,cy0=PREP_WORK_H,cx1=0,cy1=0;
        w->queue[0]=i;w->visited[i]=1;++r->components;
        while(head<tail) {
            unsigned p=w->queue[head++];int dx,dy;
            x=p%PREP_WORK_W;y=p/PREP_WORK_W;
            if(x<cx0) cx0=x;
            if(x>cx1) cx1=x;
            if(y<cy0) cy0=y;
            if(y>cy1) cy1=y;
            for(dy=-1;dy<=1;++dy) for(dx=-1;dx<=1;++dx) {
                int nx=(int)x+dx,ny=(int)y+dy;unsigned np;
                if(nx<0 || nx>=(int)PREP_WORK_W || ny<0 || ny>=(int)PREP_WORK_H) continue;
                np=(unsigned)ny*PREP_WORK_W+(unsigned)nx;
                if(!w->visited[np] && w->ink[np]>=r->threshold) {
                    w->visited[np]=1;w->queue[tail++]=np;
                }
            }
        }
        if(tail>=30U && cx1-cx0+1U>=3U && cy1-cy0+1U>=5U &&
           (cx1-cx0+1U)*100U<=PREP_WORK_W*45U &&
           (cy1-cy0+1U)*100U<=PREP_WORK_H*55U) {
            ++r->kept;r->foreground_pixels+=tail;
            if(cx0<x0) x0=cx0;
            if(cx1>x1) x1=cx1;
            if(cy0<y0) y0=cy0;
            if(cy1>y1) y1=cy1;
        }
    }
    if(!r->kept) return r->mean_gray<24U ? PREP_DARK:PREP_BLANK;
    r->bbox_x=x0;r->bbox_y=y0;r->bbox_w=x1-x0+1U;r->bbox_h=y1-y0+1U;
    if(r->mean_gray<24U) return PREP_DARK;
    if(x0<4U || y0<4U || x1>=PREP_WORK_W-4U || y1>=PREP_WORK_H-4U) return PREP_EDGE;
    return PREP_OK;
}
static void crop_normalize(PrepWorkspace *w,PrepReport *r)
{
    unsigned margin,side=r->bbox_w>r->bbox_h ? r->bbox_w:r->bbox_h;
    unsigned x,y,x1,y1,n=0;uint32_t hist[256]={0};
    margin=round_even(side,10U);if(margin<8U) margin=8U;
    r->crop_x=r->bbox_x>margin ? r->bbox_x-margin:0;
    r->crop_y=r->bbox_y>margin ? r->bbox_y-margin:0;
    x1=r->bbox_x+r->bbox_w+margin;if(x1>PREP_WORK_W) x1=PREP_WORK_W;
    y1=r->bbox_y+r->bbox_h+margin;if(y1>PREP_WORK_H) y1=PREP_WORK_H;
    r->crop_w=x1-r->crop_x;r->crop_h=y1-r->crop_y;
    for(y=r->crop_y;y<y1;++y) for(x=r->crop_x;x<x1;++x) {
        unsigned v=w->ink[y*PREP_WORK_W+x];if(v) {++hist[v];++n;}
    }
    r->high_milli=n ? quantile_milli(hist,n,995U):1000U;
    if(r->high_milli<1000U) r->high_milli=1000U;
    for(y=0;y<r->crop_h;++y) for(x=0;x<r->crop_w;++x) {
        unsigned v=(unsigned)w->ink[(r->crop_y+y)*PREP_WORK_W+r->crop_x+x]*180000U/r->high_milli;
        w->crop[y*r->crop_w+x]=(uint8_t)(v>255U ? 255U:v);
    }
}
static double cubic(double x)
{
    const double a=-0.75;x=x<0 ? -x:x;
    if(x<=1.0) return ((a+2.0)*x-(a+3.0))*x*x+1.0;
    if(x<2.0) return ((a*x-5.0*a)*x+8.0*a)*x-4.0*a;
    return 0.0;
}
static void resize_canvas(const PrepWorkspace *w,PrepReport *r,uint8_t *output)
{
    unsigned cw=r->crop_w,ch=r->crop_h,side=cw>ch ? cw:ch,x,y;
    unsigned rw=round_even(cw*56U,side),rh=round_even(ch*56U,side),ox,oy;
    if(!rw) rw=1;
    if(!rh) rh=1;
    r->resized_w=rw;r->resized_h=rh;ox=(64U-rw)/2U;oy=(64U-rh)/2U;
    for(y=0;y<rh;++y) for(x=0;x<rw;++x) {
        unsigned value;
        if(side>=56U) {
            unsigned sx,sy,x0=x*cw,x1=(x+1U)*cw,y0=y*ch,y1=(y+1U)*ch;uint64_t sum=0;
            for(sy=y0/rh;sy<(y1+rh-1U)/rh;++sy) {
                unsigned yl=y0>sy*rh ? y0:sy*rh,yr=y1<(sy+1U)*rh ? y1:(sy+1U)*rh;
                for(sx=x0/rw;sx<(x1+rw-1U)/rw;++sx) {
                    unsigned xl=x0>sx*rw ? x0:sx*rw,xr=x1<(sx+1U)*rw ? x1:(sx+1U)*rw;
                    sum+=(uint64_t)w->crop[sy*cw+sx]*(yr-yl)*(xr-xl);
                }
            }
            value=(unsigned)((sum+cw*ch/2U)/(cw*ch));
        } else {
            double fx=((double)x+0.5)*cw/rw-0.5,fy=((double)y+0.5)*ch/rh-0.5,sum=0.0;
            int ix=(int)fx,iy=(int)fy,dx,dy;
            if(fx<ix) --ix;
            if(fy<iy) --iy;
            for(dy=-1;dy<=2;++dy) for(dx=-1;dx<=2;++dx) {
                int sx=ix+dx,sy=iy+dy;
                if(sx<0) sx=0;
                if(sx>=(int)cw) sx=(int)cw-1;
                if(sy<0) sy=0;
                if(sy>=(int)ch) sy=(int)ch-1;
                sum+=w->crop[(unsigned)sy*cw+(unsigned)sx]*cubic(fx-ix-dx)*cubic(fy-iy-dy);
            }
            value=sum<=0 ? 0U:sum>=255 ? 255U:(unsigned)(sum+0.5);
        }
        output[(oy+y)*64U+ox+x]=(uint8_t)value;
    }
}
PrepCode prep_from_filtered(PrepWorkspace *w,uint8_t out[PREP_INPUT_N],PrepReport *r,const PrepClock *clock)
{
    uint32_t start=now(clock),t;PrepCode code;
    if(!w || !out || !r) {
        if(out) memset(out,0,PREP_INPUT_N);
        if(r) {memset(r,0,sizeof(*r));r->version=PREP_VERSION;r->code=PREP_BAD_ARGUMENT;}
        return PREP_BAD_ARGUMENT;
    }
    memset(r,0,sizeof(*r));r->version=PREP_VERSION;memset(out,0,PREP_INPUT_N);
    r->detect_crc=prep_crc32(w->detection,PREP_DETECT_N);
    t=now(clock);code=components(w,r);r->stage_us[3]=elapsed(clock,t);
    if(code==PREP_OK) {
        t=now(clock);crop_normalize(w,r);r->stage_us[4]=elapsed(clock,t);
        if(r->high_milli<12000U) code=PREP_WEAK;
        else {t=now(clock);resize_canvas(w,r,out);r->stage_us[5]=elapsed(clock,t);}
    }
    r->code=(uint32_t)code;r->input_crc=prep_crc32(out,PREP_INPUT_N);r->total_us=elapsed(clock,start);
    return code;
}
