/* 由phase5/prepare_data.py生成；坐标单位为埃，原子/键索引从0开始。 */
#ifndef MOLECULE_MODELS_H
#define MOLECULE_MODELS_H
#include <stddef.h>
#include <stdint.h>
#define MOL3D_MODEL_COUNT 22U
#define MOL3D_CLASS_COUNT 22U
typedef struct { uint8_t atomic_number; float x, y, z; } Mol3DAtom;
/* order: 1单键、2双键、3三键、4芳香键；不允许把4静默当单键。 */
typedef struct { uint16_t a, b; uint8_t order; } Mol3DBond;
typedef struct {
    unsigned class_id;
    const char *molecule_id, *formula;
    uint16_t atom_count, bond_count;
    float coordinate_radius;
    const Mol3DAtom *atoms;
    const Mol3DBond *bonds;
} Mol3DModel;
extern const Mol3DModel mol3d_models[MOL3D_MODEL_COUNT];
/* 未提供模型的类别返回NULL；通过class_id查找模型。 */
const Mol3DModel *mol3d_model_by_class(unsigned class_id);
#endif
