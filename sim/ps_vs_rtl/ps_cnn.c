/* Complete single-thread CPU baseline for the frozen CNN3 QAT network.
 * CHW uint8 activations; signed int8 weights; int32 MAC; int64 Q30.
 * This file never maps or accesses hardware. Each context owns its workspace.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef struct {
    int8_t weights[179832];
    int32_t biases[190], multipliers[4];
    uint8_t padded[24*34*34], pool1[24*32*32];
    uint8_t pool2[48*16*16], pool3[48*8*8], hidden[48];
} CpuCnn;

/* Ties away from zero, followed by ReLU and saturation. No signed shift. */
static inline uint8_t quantize(int32_t acc, int32_t multiplier) {
    int64_t p = (int64_t)acc * multiplier;
    if (p <= 0) return 0;
    int64_t q = (p + (INT64_C(1)<<29)) / (INT64_C(1)<<30);
    return (uint8_t)(q > 127 ? 127 : q);
}
API uint8_t pscnn_quantize(int32_t acc, int32_t multiplier) { return quantize(acc,multiplier); }

API void *pscnn_create(const int8_t *weights, unsigned nw,
                      const int32_t *biases, unsigned nb,
                      const int32_t *multipliers, unsigned nm) {
    if (!weights || !biases || !multipliers || nw!=179832 || nb!=190 || nm!=4) return NULL;
    for (unsigned i=0;i<4;i++) if (multipliers[i]<0) return NULL;
    CpuCnn *c=(CpuCnn*)calloc(1,sizeof(CpuCnn));
    if (!c) return NULL;
    memcpy(c->weights,weights,sizeof(c->weights));
    memcpy(c->biases,biases,sizeof(c->biases));
    memcpy(c->multipliers,multipliers,sizeof(c->multipliers));
    return c;
}

API void pscnn_destroy(void *context) { free(context); }

static void conv_pool(CpuCnn *c, const uint8_t *input, int ci, int co,
                      int h, int w, const int8_t *weights,
                      const int32_t *biases, int32_t multiplier,
                      uint8_t *output, int32_t *trace_acc, uint8_t *trace_relu) {
    int ph=h+2,pw=w+2,plane=ph*pw,oh=h/2,ow=w/2;
    memset(c->padded,0,(size_t)ci*plane);
    for(int i=0;i<ci;i++) for(int y=0;y<h;y++)
        memcpy(c->padded+i*plane+(y+1)*pw+1,input+(i*h+y)*w,(size_t)w);
    for(int o=0;o<co;o++) for(int y=0;y<h;y++) {
        int32_t row[64];
        for(int x=0;x<w;x++) row[x]=biases[o];
        /* Contiguous x loop permits compiler vectorization, no im2col library. */
        for(int i=0;i<ci;i++) for(int ky=0;ky<3;ky++) for(int kx=0;kx<3;kx++) {
            int32_t weight=weights[((o*ci+i)*3+ky)*3+kx];
            const uint8_t *src=c->padded+i*plane+(y+ky)*pw+kx;
            for(int x=0;x<w;x++) row[x]+=weight*src[x];
        }
        if(trace_acc) memcpy(trace_acc+(o*h+y)*w,row,(size_t)w*sizeof(int32_t));
        for(int x=0;x<w;x++) {
            uint8_t value=quantize(row[x],multiplier);
            if(trace_relu) trace_relu[(o*h+y)*w+x]=value;
            uint8_t *dst=output+(o*oh+y/2)*ow+x/2;
            if(!(y&1) && !(x&1)) *dst=value;
            else if(value>*dst) *dst=value;
        }
    }
}

static int infer_body(CpuCnn *c,const uint8_t *input,int32_t *logits,void **trace) {
    if(!c || !input || !logits) return -1;
    conv_pool(c,input,1,24,64,64,c->weights,c->biases,c->multipliers[0],c->pool1,
              trace?(int32_t*)trace[0]:NULL,trace?(uint8_t*)trace[1]:NULL);
    if(trace) memcpy(trace[2],c->pool1,sizeof(c->pool1));
    conv_pool(c,c->pool1,24,48,32,32,c->weights+216,c->biases+24,c->multipliers[1],c->pool2,
              trace?(int32_t*)trace[3]:NULL,trace?(uint8_t*)trace[4]:NULL);
    if(trace) memcpy(trace[5],c->pool2,sizeof(c->pool2));
    conv_pool(c,c->pool2,48,48,16,16,c->weights+10584,c->biases+72,c->multipliers[2],c->pool3,
              trace?(int32_t*)trace[6]:NULL,trace?(uint8_t*)trace[7]:NULL);
    if(trace) memcpy(trace[8],c->pool3,sizeof(c->pool3));
    for(int o=0;o<48;o++) {
        int32_t acc=c->biases[120+o];
        const int8_t *weight=c->weights+31320+o*3072;
        for(int i=0;i<3072;i++) acc+=(int32_t)weight[i]*c->pool3[i];
        c->hidden[o]=quantize(acc,c->multipliers[3]);
        if(trace) ((int32_t*)trace[9])[o]=acc;
    }
    if(trace) memcpy(trace[10],c->hidden,sizeof(c->hidden));
    for(int o=0;o<22;o++) {
        int32_t acc=c->biases[168+o];
        const int8_t *weight=c->weights+178776+o*48;
        for(int i=0;i<48;i++) acc+=(int32_t)weight[i]*c->hidden[i];
        logits[o]=acc;
    }
    return 0;
}

API int pscnn_infer(void *c,const uint8_t *input,int32_t *logits) {
    return infer_body((CpuCnn*)c,input,logits,NULL);
}

API int pscnn_trace(void *c,const uint8_t *input,int32_t *logits,void **trace) {
    if(!trace) return -1;
    for(int i=0;i<11;i++) if(!trace[i]) return -1;
    return infer_body((CpuCnn*)c,input,logits,trace);
}
