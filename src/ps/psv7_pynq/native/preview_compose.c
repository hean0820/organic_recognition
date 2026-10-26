#include "preview_compose.h"
#include "phase1_config.h"
#include <string.h>

PreviewLayout preview_layout(int mode_1080)
{
    PreviewLayout p;
    if (mode_1080) {
        p.width=1920; p.height=1080;
        p.camera_x=24; p.camera_y=24; p.camera_width=1280; p.camera_height=720;
    } else {
        p.width=1280; p.height=720;
        p.camera_x=16; p.camera_y=16; p.camera_width=768; p.camera_height=432;
    }
    return p;
}

static void fill_rect(uint8_t *dst, const PreviewLayout *p, unsigned x,
                      unsigned y, unsigned w, unsigned h, uint8_t shade)
{
    unsigned row;
    for (row=0; row<h; ++row)
        memset(dst+((size_t)(y+row)*p->width+x)*3U, shade, (size_t)w*3U);
}

void preview_background(uint8_t *dst, const PreviewLayout *p)
{
    memset(dst, 0x12, (size_t)p->width*p->height*3U);
    fill_rect(dst,p,p->camera_x,p->camera_y,p->camera_width,p->camera_height,0x30);
    if (p->width==1920) {
        fill_rect(dst,p,1328,24,568,480,0x28);
        fill_rect(dst,p,1328,528,568,528,0x20);
        fill_rect(dst,p,24,768,1280,288,0x1c);
    } else {
        fill_rect(dst,p,800,16,464,304,0x28);
        fill_rect(dst,p,800,336,464,368,0x20);
        fill_rect(dst,p,16,464,768,240,0x1c);
    }
}

/* 只在诊断画面生成彩条；复制摄像头时保留原始三字节顺序。 */
void preview_pattern(uint8_t *dst, const PreviewLayout *p)
{
    static const uint8_t bars[8][3] = {
        {255,255,255},{0,255,255},{255,255,0},{0,255,0},
        {255,0,255},{0,0,255},{255,0,0},{0,0,0}
    };
    unsigned x,y;
    for(y=0;y<p->camera_height;++y) {
        uint8_t *row=dst+((size_t)(p->camera_y+y)*p->width+p->camera_x)*3U;
        for(x=0;x<p->camera_width;++x) {
            const uint8_t *rgb=bars[x*8U/p->camera_width];
            row[x*3U]=rgb[0]; row[x*3U+1U]=rgb[1]; row[x*3U+2U]=rgb[2];
        }
    }
}

int preview_compose(uint8_t *dst, size_t dst_bytes, const uint8_t *src,
                    size_t src_bytes, const PreviewLayout *p)
{
    unsigned x,y;
    if (!dst || !src || !p || !p->width || !p->height ||
        !p->camera_width || !p->camera_height ||
        p->camera_x>p->width || p->camera_width>p->width-p->camera_x ||
        p->camera_y>p->height || p->camera_height>p->height-p->camera_y ||
        dst_bytes<(size_t)p->width*p->height*3U || src_bytes<CAMERA_FRAME_BYTES)
        return -1;
    if (p->camera_width==CAMERA_WIDTH && p->camera_height==CAMERA_HEIGHT) {
        for(y=0;y<CAMERA_HEIGHT;++y)
            memcpy(dst+((size_t)(p->camera_y+y)*p->width+p->camera_x)*3U,
                   src+(size_t)y*CAMERA_STRIDE,CAMERA_STRIDE);
    } else if(p->camera_width==768U && p->camera_height==432U) {
        /* Exact 5:3 nearest-neighbour mapping, without per-pixel division. */
        for(y=0;y<432U;++y) {
            const uint8_t *in=src+(size_t)(y*5U/3U)*CAMERA_STRIDE;
            uint8_t *out=dst+((size_t)(p->camera_y+y)*p->width+p->camera_x)*3U;
            for(x=0;x<256U;++x,in+=15,out+=9) {
                memcpy(out,in,3);memcpy(out+3,in+3,3);memcpy(out+6,in+9,3);
            }
        }
    } else {
        /* 预览用最近邻；CNN预处理将另外实现，不复用本缩放算法。 */
        for(y=0;y<p->camera_height;++y) {
            const uint8_t *input=src+(size_t)(y*CAMERA_HEIGHT/p->camera_height)*CAMERA_STRIDE;
            uint8_t *output=dst+((size_t)(p->camera_y+y)*p->width+p->camera_x)*3U;
            for(x=0;x<p->camera_width;++x) {
                unsigned sx=x*CAMERA_WIDTH/p->camera_width;
                output[x*3U]=input[sx*3U];
                output[x*3U+1U]=input[sx*3U+1U];
                output[x*3U+2U]=input[sx*3U+2U];
            }
        }
    }
    return 0;
}

#include "preprocess.h"
void preview_camera_roi(uint8_t *d,const PreviewLayout *p)
{
    /* Same source ROI and four display-pixel border as the former HDMI overlay.
       Call only for camera mode; never alter the camera DMA/CNN source image. */
    unsigned x,y;
    unsigned left=p->camera_x+SOURCE_ROI_LEFT*p->camera_width/CAMERA_WIDTH;
    unsigned right=p->camera_x+(SOURCE_ROI_LEFT+SOURCE_ROI_WIDTH)*p->camera_width/CAMERA_WIDTH;
    unsigned top=p->camera_y+SOURCE_ROI_TOP*p->camera_height/CAMERA_HEIGHT;
    unsigned bottom=p->camera_y+(SOURCE_ROI_TOP+SOURCE_ROI_HEIGHT)*p->camera_height/CAMERA_HEIGHT;
    for(y=top;y<bottom;++y) {
        unsigned end=y<top+4U || y>=bottom-4U ? right:left+4U;
        for(x=left;x<end;++x) {
            size_t at=((size_t)y*p->width+x)*3U;
            d[at]=0;d[at+1]=255;d[at+2]=0;
        }
        if(end!=right) for(x=right-4U;x<right;++x) {
            size_t at=((size_t)y*p->width+x)*3U;
            d[at]=0;d[at+1]=255;d[at+2]=0;
        }
    }
}

void prep_preview_guide(uint8_t *d,const PreviewLayout *p)
{
    /* Draw only on the preview copy: safe area corresponding to the 8% trim. */
    unsigned x,y;
    unsigned left=p->camera_x+(SOURCE_ROI_LEFT+PREP_TRIM_X0*SOURCE_ROI_WIDTH/PREP_DETECT_W)*p->camera_width/CAMERA_WIDTH;
    unsigned right=p->camera_x+(SOURCE_ROI_LEFT+(PREP_TRIM_X0+PREP_WORK_W)*SOURCE_ROI_WIDTH/PREP_DETECT_W)*p->camera_width/CAMERA_WIDTH;
    unsigned top=p->camera_y+(SOURCE_ROI_TOP+PREP_TRIM_Y0*SOURCE_ROI_HEIGHT/PREP_DETECT_H)*p->camera_height/CAMERA_HEIGHT;
    unsigned bottom=p->camera_y+(SOURCE_ROI_TOP+(PREP_TRIM_Y0+PREP_WORK_H)*SOURCE_ROI_HEIGHT/PREP_DETECT_H)*p->camera_height/CAMERA_HEIGHT;
    for(y=top;y<=bottom;++y) {
        unsigned end=(y==top || y==bottom)?right:left;
        for(x=left;x<=end;++x) if(((x+y)/6U)%2U==0U) {
            size_t o=((size_t)y*p->width+x)*3U;d[o]=0;d[o+1]=220;d[o+2]=220;
        }
        if(end!=right && ((right+y)/6U)%2U==0U) {
            size_t o=((size_t)y*p->width+right)*3U;d[o]=0;d[o+1]=220;d[o+2]=220;
        }
    }
}
