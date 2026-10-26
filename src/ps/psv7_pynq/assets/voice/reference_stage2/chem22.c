#include "chem22.h"
#include "chem22_weights.h"
#include <math.h>
#include <string.h>
#define FRAME 400
#define HOP 160
#define FFTN 512
#define MF 298
static float mel[40*MF],re[FFTN],im[FFTN],spectrum[257];
static float input[3840],a[8*20*48],b[16*10*24],c[24*5*12],hidden[64];
const char *chem22_model_version(void){return "chem22_real4_v1_candidate";}
static float signal_at(const int16_t *pcm,size_t count,int i,float dc){
    return i>=0 && (size_t)i<count ? pcm[i]/32768.0f-dc : 0.0f;
}
static void fft(void){
    unsigned int i,j,n,k;
    for(i=1,j=0;i<FFTN;i++){
        unsigned int bit=FFTN>>1;
        for(;j&bit;bit>>=1)j^=bit;
        j^=bit;
        if(i<j){float t=re[i];re[i]=re[j];re[j]=t;t=im[i];im[i]=im[j];im[j]=t;}
    }
    for(n=2;n<=FFTN;n<<=1){
        unsigned int half=n>>1,step=FFTN/n;
        for(i=0;i<FFTN;i+=n)for(k=0;k<half;k++){
            float wr=fft_cos[k*step],wi=-fft_sin[k*step];
            float tr=wr*re[i+k+half]-wi*im[i+k+half];
            float ti=wr*im[i+k+half]+wi*re[i+k+half];
            re[i+k+half]=re[i+k]-tr;im[i+k+half]=im[i+k]-ti;
            re[i+k]+=tr;im[i+k]+=ti;
        }
    }
}
int chem22_frontend(const int16_t *pcm,size_t count,float *out){
    int frames,i,j,k,start=0,end,nf,first=-1,last=-1;
    int64_t sum=0;float dc,maxrms=0,threshold;
    double mean=0,var=0;
    if(!pcm||!out||count==0||count>48000)return -1;
    for(i=0;i<(int)count;i++)sum+=pcm[i];
    dc=(float)((double)sum/((double)count*32768.0));
    end=count<FRAME?FRAME:(int)count;
    frames=(end-FRAME)/HOP+1;
    for(i=0;i<frames;i++){
        double energy=0;
        for(j=0;j<FRAME;j++){float v=signal_at(pcm,count,i*HOP+j,dc);energy+=(double)v*v;}
        re[i]=(float)sqrt(energy/FRAME);if(re[i]>maxrms)maxrms=re[i];
    }
    threshold=fmaxf(maxrms*.12f,.0001f);
    for(i=0;i<frames;i++)if(re[i]>threshold){if(first<0)first=i;last=i;}
    if(first>=0){start=first*HOP-1280;if(start<0)start=0;end=last*HOP+FRAME+1280;if(end>(int)count)end=(int)count;}
    if(end-start<FRAME)end=start+FRAME;
    nf=(end-start-FRAME)/HOP+1;if(nf>MF)return -1;
    for(i=0;i<nf;i++){
        memset(re,0,sizeof(re));memset(im,0,sizeof(im));
        for(j=0;j<FRAME;j++){
            int at=start+i*HOP+j;
            float v=signal_at(pcm,count,at,dc);
            if(at>start)v-=.97f*signal_at(pcm,count,at-1,dc);
            re[j]=v*hann_window[j];
        }
        fft();for(j=0;j<257;j++)spectrum[j]=re[j]*re[j]+im[j]*im[j];
        for(j=0;j<40;j++){
            float power=0;for(k=0;k<257;k++)power+=mel_bank[j*257+k]*spectrum[k];
            mel[j*MF+i]=logf(fmaxf(power,1e-10f));
        }
    }
    for(j=0;j<40;j++)for(i=0;i<96;i++){
        float t=i*(nf-1)/95.0f;int lo=(int)t,hi=lo+1;float w=t-lo;
        if(hi>=nf)hi=nf-1;
        out[j*96+i]=mel[j*MF+lo]*(1-w)+mel[j*MF+hi]*w;mean+=out[j*96+i];
    }
    mean/=3840;
    for(i=0;i<3840;i++){double v=out[i]-mean;var+=v*v;}
    var=sqrt(var/3840);if(var<1)var=1;
    for(i=0;i<3840;i++){float v=(float)((out[i]-mean)/var);out[i]=fminf(4,fmaxf(-4,v));}
    return 0;
}
static void conv(const float *x,int ci,int ih,int iw,const float *weight,const float *bias,int co,float *y){
    int oh=(ih+1)/2,ow=(iw+1)/2,o,h,w,d,kh,kw;
    for(o=0;o<co;o++)for(h=0;h<oh;h++)for(w=0;w<ow;w++){
        float value=bias[o];
        for(d=0;d<ci;d++)for(kh=0;kh<3;kh++)for(kw=0;kw<3;kw++){
            int yy=h*2+kh-1,xx=w*2+kw-1;
            if(yy>=0&&yy<ih&&xx>=0&&xx<iw)value+=x[(d*ih+yy)*iw+xx]*weight[((o*ci+d)*3+kh)*3+kw];
        }
        y[(o*oh+h)*ow+w]=value>0?value:0;
    }
}
void chem22_logits(const float *x,float *out){
    int i,j;
    conv(x,1,40,96,layers_0_weight,layers_0_bias,8,a);
    conv(a,8,20,48,layers_2_weight,layers_2_bias,16,b);
    conv(b,16,10,24,layers_4_weight,layers_4_bias,24,c);
    for(i=0;i<64;i++){float v=layers_7_bias[i];for(j=0;j<1440;j++)v+=c[j]*layers_7_weight[i*1440+j];hidden[i]=v>0?v:0;}
    for(i=0;i<24;i++){float v=layers_9_bias[i];for(j=0;j<64;j++)v+=hidden[j]*layers_9_weight[i*64+j];out[i]=v;}
}
int chem22_predict_pcm(const int16_t *pcm,size_t count,Chem22Result *r){
    float logits[24],best=-1e30f,second=-1e30f,total=0;int i,top=0;
    int64_t sum=0;double rms=0,dc;
    if(!r)return -1;
    memset(r,0,sizeof(*r));r->class_id=-1;r->raw_class=-1;r->reason=3;
    if(!pcm||count<400||count>48000)return -1;
    for(i=0;i<(int)count;i++)sum+=pcm[i];
    dc=(double)sum/count;
    for(i=0;i<(int)count;i++){double v=(pcm[i]-dc)/32768.0;rms+=v*v;}
    if(sqrt(rms/count)<.0005){r->raw_class=23;r->reason=2;return 0;}
    if(chem22_frontend(pcm,count,input)!=0)return -1;
    chem22_logits(input,logits);
    for(i=0;i<24;i++)if(logits[i]>best){second=best;best=logits[i];top=i;}else if(logits[i]>second)second=logits[i];
    for(i=0;i<24;i++)total+=expf(logits[i]-best);
    r->confidence=1.0f/total;r->margin=(1-expf(second-best))/total;r->raw_class=top;
    if(top<22&&r->confidence>=CHEM22_THRESHOLD&&r->margin>=CHEM22_MARGIN){r->class_id=top;r->reason=0;}
    else r->reason=top==23?2:1;
    return 0;
}
