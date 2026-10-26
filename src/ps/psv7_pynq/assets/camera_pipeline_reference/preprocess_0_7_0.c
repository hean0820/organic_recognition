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
uint32_t prep_crc32(const uint8_t *p,size_t n)
{
    uint32_t crc=UINT32_C(0xffffffff);size_t i;unsigned k;
    for(i=0;i<n;++i) {
        crc^=p[i];for(k=0;k<8;++k) crc=(crc>>1)^((0U-(crc&1U))&UINT32_C(0xedb88320));
    }
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
