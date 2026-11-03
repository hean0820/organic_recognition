#include "prep_accel.h"
#ifdef __SYNTHESIS__
#include <ap_int.h>
typedef ap_uint<5> InkWeight;
#else
typedef uint8_t InkWeight;
#endif
static const uint8_t kernel[67]={0,0,0,1,0,0,1,0,1,1,1,1,2,1,3,2,3,3,4,4,5,5,5,6,7,7,8,8,8,9,9,9,9,10,9,9,9,9,8,8,8,7,7,6,5,5,5,4,4,3,3,2,3,1,2,1,1,1,1,0,1,0,0,1,0,0,0};
static int reflect(int x,int n) {
#pragma HLS INLINE
    return x<0 ? -x:x>=n ? 2*n-2-x:x;
}
static void make_detection(const uint32_t *frame,uint32_t *detection,uint32_t stride) {
    uint8_t rows[3][960];uint32_t packed_row[720];int tags[3]={-1,-1,-1};
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
#pragma HLS ARRAY_PARTITION variable=rows cyclic factor=2 dim=2
#pragma HLS ARRAY_PARTITION variable=tags complete
    for(int y=0;y<267;++y) {
        int y0=y*400,y1=(y+1)*400,first=y0/267,last=(y1+266)/267;
        for(int j=0;j<3;++j) {
            int sy=first+j;
            if(sy<last && tags[sy%3]!=sy) {
                int bank=sy%3;
                for(int i=0;i<720;++i) {
#pragma HLS PIPELINE II=1
                    packed_row[i]=frame[(160+sy)*stride+120+i];
                }
                for(int sx=0;sx<960;++sx) {
#pragma HLS PIPELINE II=1
                    int p=3*sx;uint32_t a=packed_row[p/4],b=packed_row[(p+2)/4];
                    uint32_t blue=(a>>((p&3)*8))&255U;
                    uint32_t green=(((p&3)==3 ? b:a)>>(((p+1)&3)*8))&255U;
                    uint32_t red=(b>>(((p+2)&3)*8))&255U;
                    rows[bank][sx]=(uint8_t)((1868U*blue+9617U*green+4899U*red+8192U)>>14);
                }
                tags[bank]=sy;
            }
        }
        uint32_t packed=0;
        for(int x=0;x<640;++x) {
#pragma HLS PIPELINE II=1
            int x0=x*960,x1=(x+1)*960,sfirst=x0/640;uint32_t sum=0;
            for(int j=0;j<3;++j) {
#pragma HLS PIPELINE II=1
                int sy=first+j;
                if(sy<last) {
                    int lo=y0>sy*267 ? y0:sy*267;
                    int hi=y1<(sy+1)*267 ? y1:(sy+1)*267;
                    for(int k=0;k<2;++k) {
#pragma HLS UNROLL
                        int sx=sfirst+k;
                        int xl=x0>sx*640 ? x0:sx*640;
                        int xr=x1<(sx+1)*640 ? x1:(sx+1)*640;
                        sum+=(uint32_t)rows[sy%3][sx]*(hi-lo)*(xr-xl);
                    }
                }
            }
            uint32_t value=(sum+192000U)/384000U;
            packed|=value<<((x&3)*8);
            if((x&3)==3) {detection[y*160+x/4]=packed;packed=0;}
        }
    }
}
static void make_gray(const uint32_t *detection,uint32_t *gray) {
    uint8_t rows[3][640];int tags[3]={-1,-1,-1};
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
#pragma HLS ARRAY_PARTITION variable=rows cyclic factor=4 dim=2
#pragma HLS ARRAY_PARTITION variable=tags complete
    for(int y=0;y<224;++y) {
        for(int k=-1;k<=1;++k) {
            int sy=reflect(y+k,224)+21,bank=sy%3;
            if(tags[bank]!=sy) {
                for(int i=0;i<160;++i) {
#pragma HLS PIPELINE II=1
                    uint32_t word=detection[sy*160+i];
                    for(int b=0;b<4;++b) {
#pragma HLS UNROLL
                        rows[bank][4*i+b]=(uint8_t)(word>>(8*b));
                    }
                }
                tags[bank]=sy;
            }
        }
        uint32_t packed=0;
        for(int x=0;x<540;++x) {
#pragma HLS PIPELINE II=1
            uint32_t sum=0;
            if(x<537) {
                for(int dy=-1;dy<=1;++dy) {
#pragma HLS UNROLL
                    for(int dx=-1;dx<=1;++dx) {
#pragma HLS UNROLL
                        int yy=reflect(y+dy,224)+21,xx=reflect(x+dx,537)+51;
                        sum+=rows[yy%3][xx]*(dy==0 ? 2U:1U)*(dx==0 ? 2U:1U);
                    }
                }
            }
            uint32_t value=x<537 ? (sum+8U)>>4:0;
            packed|=value<<((x&3)*8);
            if((x&3)==3) {gray[y*135+x/4]=packed;packed=0;}
        }
    }
}
static void make_horizontal(const uint32_t *gray,uint32_t *horizontal) {
    uint8_t row[540],window[67];
#pragma HLS ARRAY_PARTITION variable=row cyclic factor=4
#pragma HLS ARRAY_PARTITION variable=window complete
    for(int y=0;y<224;++y) {
        for(int i=0;i<135;++i) {
#pragma HLS PIPELINE II=1
            uint32_t word=gray[y*135+i];
            for(int b=0;b<4;++b) {
#pragma HLS UNROLL
                row[4*i+b]=(uint8_t)(word>>(8*b));
            }
        }
        for(int k=0;k<67;++k) {
#pragma HLS PIPELINE II=1
            window[k]=row[reflect(k-33,537)];
        }
        uint32_t packed=0;
        for(int x=0;x<538;++x) {
#pragma HLS PIPELINE II=1
            uint32_t sum=0;
            if(x<537) for(int k=0;k<67;++k) {
#pragma HLS UNROLL
                sum+=(uint32_t)window[k]*kernel[k];
            }
            packed|=sum<<((x&1)*16);
            if(x&1) {horizontal[y*269+x/2]=packed;packed=0;}
            if(x<536) {
                for(int k=0;k<66;++k) {
#pragma HLS UNROLL
                    window[k]=window[k+1];
                }
                window[66]=row[reflect(x+34,537)];
            }
        }
    }
}
/* Each physical row bank has one fixed read per pixel. At reflected borders,
   mirrored weights are added to the corresponding real row, rather than
   muxing 67 independent random reads across 67 BRAM banks. */
static uint8_t vertical_weight(int row,int y) {
#pragma HLS INLINE
    int d=row-y;unsigned value=0;
    if(d>=-33 && d<=33) value=kernel[d+33];
    if(row>0 && row+y<=33) value+=kernel[33-row-y];
    if(row<223 && 446-row-y<=33) value+=kernel[33+446-row-y];
    return (uint8_t)value;
}
static void make_ink(const uint32_t *gray,const uint32_t *horizontal,uint32_t *ink) {
    uint16_t ring[67][537];uint8_t tags[67],rowgray[540];InkWeight weights[67];
#pragma HLS ARRAY_PARTITION variable=ring complete dim=1
#pragma HLS BIND_STORAGE variable=ring type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=tags complete
#pragma HLS ARRAY_PARTITION variable=weights complete
    for(int bank=0;bank<67;++bank) tags[bank]=255;
    for(int y=0;y<224;++y) {
        int lo=y>33 ? y-33:0,hi=y+33<223 ? y+33:223;
        for(int src=lo;src<=hi;++src) {
#pragma HLS LOOP_TRIPCOUNT min=34 max=67
            int bank=src<67 ? src:src<134 ? src-67:src<201 ? src-134:src-201;
            if(tags[bank]!=src) {
                for(int i=0;i<269;++i) {
#pragma HLS PIPELINE II=1
                    uint32_t word=horizontal[src*269+i];
                    ring[bank][2*i]=(uint16_t)word;
                    if(2*i+1<537) ring[bank][2*i+1]=(uint16_t)(word>>16);
                }
                tags[bank]=src;
            }
        }
        for(int bank=0;bank<67;++bank) {
#pragma HLS PIPELINE II=1
            weights[bank]=tags[bank]==255 ? 0:vertical_weight(tags[bank],y);
        }
        for(int i=0;i<135;++i) {
#pragma HLS PIPELINE II=1
            uint32_t word=gray[y*135+i];
            for(int b=0;b<4;++b) {
#pragma HLS UNROLL
                rowgray[4*i+b]=(uint8_t)(word>>(8*b));
            }
        }
        uint32_t packed=0;
        for(int x=0;x<540;++x) {
#pragma HLS PIPELINE II=1
            uint32_t sum=0,value=0;
            if(x<537) {
                for(int bank=0;bank<67;++bank) {
#pragma HLS UNROLL
                    if(weights[bank]) sum+=(uint32_t)ring[bank][x]*weights[bank];
                }
                uint32_t background=(sum+32768U)>>16;
                value=background>rowgray[x] ? background-rowgray[x]:0;
            }
            packed|=value<<((x&3)*8);
            if((x&3)==3) {ink[y*135+x/4]=packed;packed=0;}
        }
    }
}
uint32_t prep_only_accel(const uint32_t *frame,uint32_t *detection,uint32_t *gray,
                    uint32_t *horizontal,uint32_t *ink,uint32_t stride_words,uint32_t mode) {
#pragma HLS INTERFACE m_axi port=frame offset=slave bundle=gmem depth=691200 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=detection offset=slave bundle=gmem depth=147720 max_read_burst_length=64 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=gray offset=slave bundle=gmem depth=30240
#pragma HLS INTERFACE m_axi port=horizontal offset=slave bundle=gmem depth=60256
#pragma HLS INTERFACE m_axi port=ink offset=slave bundle=gmem depth=30240
#pragma HLS INTERFACE s_axilite port=frame bundle=control
#pragma HLS INTERFACE s_axilite port=detection bundle=control
#pragma HLS INTERFACE s_axilite port=gray bundle=control
#pragma HLS INTERFACE s_axilite port=horizontal bundle=control
#pragma HLS INTERFACE s_axilite port=ink bundle=control
#pragma HLS INTERFACE s_axilite port=stride_words bundle=control
#pragma HLS INTERFACE s_axilite port=mode bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if(mode==4) return 0x50525001U;
    if(mode>1 || stride_words<960 || stride_words>4096) return 1;
    if(mode==0) make_detection(frame,detection,stride_words);
    make_gray(detection,gray);
    make_horizontal(gray,horizontal);
    make_ink(gray,horizontal,ink);
    return 0;
}
