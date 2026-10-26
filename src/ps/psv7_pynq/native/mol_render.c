#include "mol_render.h"
#include <math.h>
#include <float.h>
#include <string.h>

typedef struct { float x,y,z; } V;
typedef struct { unsigned char b,g,r; } Color;
typedef struct { MolSurface *s; float scale,cx,cy; } View;
static V add(V a,V b) {V r={a.x+b.x,a.y+b.y,a.z+b.z};return r;}
static V sub(V a,V b) {V r={a.x-b.x,a.y-b.y,a.z-b.z};return r;}
static V mul(V a,float k) {V r={a.x*k,a.y*k,a.z*k};return r;}
static float dot(V a,V b) {return a.x*b.x+a.y*b.y+a.z*b.z;}
static V pos(const Mol3DAtom *a) {V r={a->x,a->y,a->z};return r;}
static V rotate(V a,float st,float ct,float sa,float ca)
{
    /* R_x(tilt) R_y(angle), applied afresh for each frame. */
    V b={ca*a.x+sa*a.z,a.y,-sa*a.x+ca*a.z};
    V r={b.x,ct*b.y-st*b.z,st*b.y+ct*b.z};return r;
}
static float radius(unsigned z) {return z==1 ? .23f:z==17 || z==35 || z==53 ? .40f:.34f;}
static Color color(unsigned z)
{
    Color c={165,165,165};
    if(z==1) {c.b=235;c.g=235;c.r=235;}
    else if(z==17) {c.b=50;c.g=210;c.r=60;}
    else if(z==8) {c.b=65;c.g=65;c.r=230;}
    else if(z==7) {c.b=235;c.g=90;c.r=70;}
    else if(z==35) {c.b=40;c.g=65;c.r=160;}
    else if(z==53) {c.b=190;c.g=60;c.r=135;}
    return c;
}
int mol_surface_init(MolSurface *s,uint8_t *c,size_t bytes,float *d,size_t n,
                     unsigned w,unsigned h,unsigned stride)
{
    if(!s || !c || !d || !w || !h || w>1024 || h>1024 || stride<w*3U ||
       bytes<(size_t)(h-1U)*stride+w*3U || n<(size_t)w*h) return -1;
    s->color=c;s->depth=d;s->width=w;s->height=h;s->stride=stride;
    s->color_bytes=bytes;s->depth_count=n;mol_surface_clear(s);return 0;
}
void mol_surface_clear(MolSurface *s)
{
    unsigned y;size_t i;
    if(!s || !s->color || !s->depth) return;
    for(y=0;y<s->height;++y) memset(s->color+(size_t)y*s->stride,28,s->width*3U);
    for(i=0;i<(size_t)s->width*s->height;++i) s->depth[i]=-FLT_MAX;
}
static void put(View *v,int x,int y,float z,V normal,Color c)
{
    size_t i=(size_t)y*v->s->width+x;
    float light,shade;uint8_t *p;
    if(z<=v->s->depth[i]) return;
    v->s->depth[i]=z;
    light=-.35f*normal.x+.45f*normal.y+.82f*normal.z;
    if(light<0) light=0;
    shade=.30f+.65f*light;
    if(shade>1) shade=1;
    p=v->s->color+(size_t)y*v->s->stride+x*3U;
    p[0]=(uint8_t)(c.b*shade);p[1]=(uint8_t)(c.g*shade);p[2]=(uint8_t)(c.r*shade);
}
static int bounds(View *v,float x0,float y0,float x1,float y1,int *b)
{
    float l=v->cx+x0*v->scale,r=v->cx+x1*v->scale;
    float t=v->cy-y1*v->scale,bt=v->cy-y0*v->scale;
    if(r<0 || bt<0 || l>=v->s->width || t>=v->s->height) return 0;
    b[0]=l<0 ? 0:(int)floorf(l);b[1]=t<0 ? 0:(int)floorf(t);
    b[2]=r>=v->s->width ? (int)v->s->width-1:(int)ceilf(r);
    b[3]=bt>=v->s->height ? (int)v->s->height-1:(int)ceilf(bt);
    return 1;
}
static void sphere(View *v,V a,float r,Color c)
{
    int b[4],x,y;
    if(!bounds(v,a.x-r,a.y-r,a.x+r,a.y+r,b)) return;
    for(y=b[1];y<=b[3];++y) for(x=b[0];x<=b[2];++x) {
        V n={(x+.5f-v->cx)/v->scale-a.x,(v->cy-y-.5f)/v->scale-a.y,0};
        float q=r*r-n.x*n.x-n.y*n.y;
        if(q<0) continue;
        n.z=sqrtf(q);put(v,x,y,a.z+n.z,mul(n,1/r),c);
    }
}
/* Exact orthographic ray/finite cylinder intersection plus spherical end caps.
   Per-pixel depth handles rods crossing rods/atoms, including end-on views. */
static void rod(View *v,V a,V b,float r,Color c)
{
    V axis=sub(b,a);float length=sqrtf(dot(axis,axis));
    int box[4],x,y;
    if(length<1e-6f) {sphere(v,a,r,c);return;}
    axis=mul(axis,1/length);
    if(!bounds(v,fminf(a.x,b.x)-r,fminf(a.y,b.y)-r,
                 fmaxf(a.x,b.x)+r,fmaxf(a.y,b.y)+r,box)) return;
    for(y=box[1];y<=box[3];++y) for(x=box[0];x<=box[2];++x) {
        V w={(x+.5f-v->cx)/v->scale-a.x,(v->cy-y-.5f)/v->scale-a.y,-a.z};
        float axial=dot(w,axis),aa=1-axis.z*axis.z;
        V perpendicular=sub(w,mul(axis,axial));
        float bb=2*(w.z-axis.z*axial),cc=dot(perpendicular,perpendicular)-r*r;
        float disc=bb*bb-4*aa*cc;
        if(aa>1e-6f && disc>=0) {
            float root=sqrtf(disc),zz[2]={(-bb+root)/(2*aa),(-bb-root)/(2*aa)};
            unsigned k;
            for(k=0;k<2;++k) {
                float t=axial+zz[k]*axis.z;
                if(t>=0 && t<=length) {
                    V n=w;n.z+=zz[k];n=sub(n,mul(axis,t));
                    put(v,x,y,zz[k],mul(n,1/r),c);
                }
            }
        }
    }
    sphere(v,a,r,c);sphere(v,b,r,c);
}
/* Pick separation direction in ORIGINAL molecular coordinates. Neighbours
   align multiple rods with the molecular plane. Linear isolated bonds get a
   deterministic orthogonal axis. Rotate this vector with the molecule. */
static V separation(const Mol3DModel *m,const Mol3DBond *bond)
{
    V a=pos(&m->atoms[bond->a]),u=sub(pos(&m->atoms[bond->b]),a),best={0,0,0};
    float norm=dot(u,u),bestn=0;unsigned j;
    u=mul(u,1/sqrtf(norm));
    for(j=0;j<m->bond_count;++j) {
        const Mol3DBond *q=&m->bonds[j];unsigned other=MOL_RENDER_MAX_ATOMS;
        if(q->a==bond->a) other=q->b;else if(q->b==bond->a) other=q->a;
        if(other<m->atom_count && other!=bond->b) {
            V w=sub(pos(&m->atoms[other]),a);float n;
            w=sub(w,mul(u,dot(w,u)));n=dot(w,w);
            if(n>bestn) {best=w;bestn=n;}
        }
    }
    if(bestn<1e-6f) {
        V ref={0,0,0};
        if(fabsf(u.x)<=fabsf(u.y) && fabsf(u.x)<=fabsf(u.z)) ref.x=1;
        else if(fabsf(u.y)<=fabsf(u.z)) ref.y=1;else ref.z=1;
        best=sub(ref,mul(u,dot(ref,u)));bestn=dot(best,best);
    }
    return mul(best,1/sqrtf(bestn));
}
int mol_render(MolSurface *s,const Mol3DModel *m,float tilt,float angle)
{
    V atoms[MOL_RENDER_MAX_ATOMS];View v;
    float extent=0,st,ct,sa,ca;unsigned i;
    if(!s || !s->color || !s->depth) return -1;
    mol_surface_clear(s);if(!m) return 0;
    if(!isfinite(tilt) || !isfinite(angle) || !m->atoms ||
       !m->atom_count || m->atom_count>MOL_RENDER_MAX_ATOMS ||
       m->bond_count>MOL_RENDER_MAX_BONDS || (m->bond_count && !m->bonds)) return -1;
    for(i=0;i<m->atom_count;++i) {
        V p=pos(&m->atoms[i]);float r;
        if(!isfinite(p.x) || !isfinite(p.y) || !isfinite(p.z) ||
           fabsf(p.x)>10000 || fabsf(p.y)>10000 || fabsf(p.z)>10000 ||
           !m->atoms[i].atomic_number || m->atoms[i].atomic_number>118) return -1;
        r=sqrtf(dot(p,p))+radius(m->atoms[i].atomic_number);
        if(r>extent) extent=r;
    }
    for(i=0;i<m->bond_count;++i) {
        const Mol3DBond *b=&m->bonds[i];V diff;
        if(b->a>=m->atom_count || b->b>=m->atom_count || b->a==b->b ||
           !b->order || b->order>3) return -1;
        diff=sub(pos(&m->atoms[b->a]),pos(&m->atoms[b->b]));
        if(dot(diff,diff)<1e-10f) return -1;
    }
    tilt=fmodf(tilt,360)*.01745329252f;angle=fmodf(angle,360)*.01745329252f;
    st=sinf(tilt);ct=cosf(tilt);sa=sinf(angle);ca=cosf(angle);
    v.s=s;v.cx=s->width*.5f;v.cy=s->height*.5f;
    /* Bounding sphere + .35 A covers multiple rod offsets at EVERY angle. */
    v.scale=(s->width<s->height ? s->width:s->height)*.46f/(extent+.35f);
    for(i=0;i<m->atom_count;++i) atoms[i]=rotate(pos(&m->atoms[i]),st,ct,sa,ca);
    for(i=0;i<m->bond_count;++i) {
        const Mol3DBond *b=&m->bonds[i];unsigned k;Color c={185,185,185};
        V offset=rotate(separation(m,b),st,ct,sa,ca);
        float spacing=b->order==2 ? .28f:.24f;
        for(k=0;k<b->order;++k) {
            V shift=mul(offset,((float)k-((float)b->order-1)*.5f)*spacing);
            rod(&v,add(atoms[b->a],shift),add(atoms[b->b],shift),b->order==1 ? .105f:.075f,c);
        }
    }
    for(i=0;i<m->atom_count;++i) sphere(&v,atoms[i],radius(m->atoms[i].atomic_number),color(m->atoms[i].atomic_number));
    return 0;
}
int mol_blit(const MolSurface *s,uint8_t *f,size_t bytes,unsigned fw,unsigned fh,
             unsigned stride,unsigned x,unsigned y)
{
    unsigned row;
    if(!s || !s->color || !f || !fw || !fh || fw>4096 || fh>4096 ||
       stride<fw*3U || bytes<(size_t)(fh-1U)*stride+fw*3U ||
       x>fw || y>fh || s->width>fw-x || s->height>fh-y) return -1;
    for(row=0;row<s->height;++row)
        memcpy(f+(size_t)(y+row)*stride+x*3U,s->color+(size_t)row*s->stride,s->width*3U);
    return 0;
}
