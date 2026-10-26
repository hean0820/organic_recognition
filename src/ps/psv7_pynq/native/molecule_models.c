/* 自动生成的只读结构数据；旋转时不修改原始坐标。 */
#include "molecule_models.h"

static const Mol3DAtom ethylene_atoms[] = {
    {6, -0.6672f, 0.0000f, 0.0000f},
    {6, 0.6672f, 0.0000f, 0.0000f},
    {1, -1.2213f, -0.9290f, 0.0708f},
    {1, -1.2212f, 0.9290f, -0.0708f},
    {1, 1.2213f, 0.9290f, -0.0708f},
    {1, 1.2213f, -0.9290f, 0.0708f},
};
static const Mol3DBond ethylene_bonds[] = {
    {0, 1, 2},
    {0, 2, 1},
    {0, 3, 1},
    {1, 4, 1},
    {1, 5, 1},
};

static const Mol3DAtom propylene_atoms[] = {
    {6, 1.1256f, -0.1379f, 0.0000f},
    {6, -0.2205f, 0.5054f, 0.0000f},
    {6, -1.3737f, -0.1719f, 0.0000f},
    {1, 1.6867f, 0.1715f, -0.8871f},
    {1, 1.0626f, -1.2307f, 0.0000f},
    {1, 1.6867f, 0.1715f, 0.8871f},
    {1, -0.2512f, 1.5914f, 0.0000f},
    {1, -2.3209f, 0.3563f, 0.0000f},
    {1, -1.3952f, -1.2560f, 0.0000f},
};
static const Mol3DBond propylene_bonds[] = {
    {0, 1, 1},
    {0, 3, 1},
    {0, 4, 1},
    {0, 5, 1},
    {1, 2, 2},
    {1, 6, 1},
    {2, 7, 1},
    {2, 8, 1},
};

static const Mol3DAtom acetylene_atoms[] = {
    {6, -0.6000f, 0.0000f, 0.0000f},
    {6, 0.6000f, 0.0000f, 0.0000f},
    {1, -1.6650f, 0.0000f, -0.0001f},
    {1, 1.6650f, 0.0000f, 0.0001f},
};
static const Mol3DBond acetylene_bonds[] = {
    {0, 1, 3},
    {0, 2, 1},
    {1, 3, 1},
};

static const Mol3DAtom propyne_atoms[] = {
    {6, -0.9550f, -0.0000f, 0.0001f},
    {6, 0.5073f, -0.0003f, 0.0002f},
    {6, 1.7077f, -0.0000f, -0.0000f},
    {1, -1.3444f, 0.0659f, 1.0205f},
    {1, -1.3441f, 0.8509f, -0.5672f},
    {1, -1.3444f, -0.9166f, -0.4532f},
    {1, 2.7727f, 0.0002f, -0.0001f},
};
static const Mol3DBond propyne_bonds[] = {
    {0, 1, 1},
    {0, 3, 1},
    {0, 4, 1},
    {0, 5, 1},
    {1, 2, 3},
    {2, 6, 1},
};

static const Mol3DAtom ethanol_atoms[] = {
    {8, -1.5367f, 0.3114f, -0.0886f},
    {6, -0.4118f, -0.5548f, -0.0886f},
    {6, 0.8520f, 0.2785f, -0.0886f},
    {1, -0.4613f, -1.2003f, 0.7933f},
    {1, -0.4607f, -1.1821f, -0.9832f},
    {1, 1.7395f, -0.3603f, -0.1063f},
    {1, 0.8771f, 0.9424f, -0.9590f},
    {1, 0.8961f, 0.9169f, 0.8000f},
    {1, -1.4946f, 0.8481f, 0.7213f},
};
static const Mol3DBond ethanol_bonds[] = {
    {0, 1, 1},
    {0, 8, 1},
    {1, 2, 1},
    {1, 3, 1},
    {1, 4, 1},
    {2, 5, 1},
    {2, 6, 1},
    {2, 7, 1},
};

static const Mol3DAtom ethylene_glycol_atoms[] = {
    {8, -1.3356f, -0.7928f, -0.0252f},
    {8, 1.4474f, -0.7928f, 0.2724f},
    {6, -0.6420f, 0.3664f, 0.4203f},
    {6, 0.7538f, 0.3664f, -0.1730f},
    {1, -1.2045f, 1.2549f, 0.1196f},
    {1, -0.6004f, 0.3224f, 1.5126f},
    {1, 1.3138f, 1.2493f, 0.1473f},
    {1, 0.7242f, 0.3408f, -1.2668f},
    {1, -1.3896f, -0.7472f, -0.9950f},
    {1, 0.9332f, -1.5678f, -0.0119f},
};
static const Mol3DBond ethylene_glycol_bonds[] = {
    {0, 2, 1},
    {0, 8, 1},
    {1, 3, 1},
    {1, 9, 1},
    {2, 3, 1},
    {2, 4, 1},
    {2, 5, 1},
    {3, 6, 1},
    {3, 7, 1},
};

static const Mol3DAtom glycerol_atoms[] = {
    {8, 0.0835f, -1.5616f, 0.0715f},
    {8, 2.4588f, -0.2167f, -0.4153f},
    {8, -2.3531f, -0.2220f, -0.4168f},
    {6, 0.0601f, -0.2247f, -0.4339f},
    {6, 1.3144f, 0.4857f, 0.0578f},
    {6, -1.2037f, 0.4655f, 0.0663f},
    {1, 0.0567f, -0.3089f, -1.5257f},
    {1, 1.3676f, 0.5064f, 1.1514f},
    {1, 1.3618f, 1.5123f, -0.3171f},
    {1, -1.2470f, 1.5013f, -0.2850f},
    {1, -1.2500f, 0.4547f, 1.1605f},
    {1, 0.0814f, -1.5156f, 1.0429f},
    {1, 2.4008f, -1.1278f, -0.0800f},
    {1, -3.1317f, 0.2511f, -0.0768f},
};
static const Mol3DBond glycerol_bonds[] = {
    {0, 3, 1},
    {0, 11, 1},
    {1, 4, 1},
    {1, 12, 1},
    {2, 5, 1},
    {2, 13, 1},
    {3, 4, 1},
    {3, 5, 1},
    {3, 6, 1},
    {4, 7, 1},
    {4, 8, 1},
    {5, 9, 1},
    {5, 10, 1},
};

static const Mol3DAtom phenol_atoms[] = {
    {8, -2.4999f, -0.0710f, -0.0003f},
    {6, -1.1388f, -0.0711f, 0.0004f},
    {6, -0.4414f, 1.1369f, 0.0003f},
    {6, -0.4415f, -1.2790f, 0.0002f},
    {6, 0.9535f, 1.1369f, -0.0000f},
    {6, 0.9534f, -1.2791f, 0.0001f},
    {6, 1.6509f, -0.0711f, -0.0001f},
    {1, -0.9728f, 2.0848f, 0.0003f},
    {1, -0.9792f, -2.2232f, 0.0001f},
    {1, 1.4968f, 2.0773f, -0.0002f},
    {1, 1.4964f, -2.2197f, -0.0001f},
    {1, 2.7370f, -0.0712f, -0.0003f},
    {1, -2.8149f, 0.8492f, -0.0004f},
};
static const Mol3DBond phenol_bonds[] = {
    {0, 1, 1},
    {0, 12, 1},
    {1, 2, 2},
    {1, 3, 1},
    {2, 4, 1},
    {2, 7, 1},
    {3, 5, 2},
    {3, 8, 1},
    {4, 6, 2},
    {4, 9, 1},
    {5, 6, 1},
    {5, 10, 1},
    {6, 11, 1},
};

static const Mol3DAtom acetic_acid_atoms[] = {
    {8, -0.7957f, 1.2644f, -0.0000f},
    {8, -1.4722f, -0.9124f, -0.0000f},
    {6, 0.8821f, -0.3762f, -0.0000f},
    {6, -0.5829f, -0.0742f, 0.0008f},
    {1, 1.3446f, 0.0324f, -0.9019f},
    {1, 1.3478f, 0.0430f, 0.8954f},
    {1, 1.0285f, -1.4602f, 0.0066f},
    {1, -1.7520f, 1.4835f, -0.0006f},
};
static const Mol3DBond acetic_acid_bonds[] = {
    {0, 3, 1},
    {0, 7, 1},
    {1, 3, 2},
    {2, 3, 1},
    {2, 4, 1},
    {2, 5, 1},
    {2, 6, 1},
};

static const Mol3DAtom formaldehyde_atoms[] = {
    {8, 1.2123f, -0.0001f, 0.0000f},
    {6, -0.0123f, -0.0001f, 0.0000f},
    {1, -0.6000f, 0.2426f, -0.8998f},
    {1, -0.6000f, -0.2424f, 0.8998f},
};
static const Mol3DBond formaldehyde_bonds[] = {
    {0, 1, 2},
    {1, 2, 1},
    {1, 3, 1},
};

static const Mol3DAtom acetaldehyde_atoms[] = {
    {8, 1.8051f, 0.3197f, 0.0001f},
    {6, -0.5966f, 0.2600f, 0.0001f},
    {6, 0.7738f, -0.3441f, 0.0001f},
    {1, -1.1330f, -0.0708f, 0.8925f},
    {1, -0.5257f, 1.3504f, 0.0017f},
    {1, -1.1320f, -0.0683f, -0.8937f},
    {1, 0.8086f, -1.4467f, -0.0006f},
};
static const Mol3DBond acetaldehyde_bonds[] = {
    {0, 2, 2},
    {1, 2, 1},
    {1, 3, 1},
    {1, 4, 1},
    {1, 5, 1},
    {2, 6, 1},
};

static const Mol3DAtom acetone_atoms[] = {
    {8, 0.0004f, -1.8512f, -0.0000f},
    {6, 0.0001f, -0.6213f, 0.0008f},
    {6, 1.2811f, 0.1683f, -0.0000f},
    {6, -1.2812f, 0.1678f, -0.0000f},
    {1, 1.3280f, 0.7894f, -0.8978f},
    {1, 1.3261f, 0.7941f, 0.8947f},
    {1, 2.1352f, -0.5145f, 0.0029f},
    {1, -2.1351f, -0.5154f, 0.0029f},
    {1, -1.3283f, 0.7889f, -0.8978f},
    {1, -1.3265f, 0.7937f, 0.8947f},
};
static const Mol3DBond acetone_bonds[] = {
    {0, 1, 2},
    {1, 2, 1},
    {1, 3, 1},
    {2, 4, 1},
    {2, 5, 1},
    {2, 6, 1},
    {3, 7, 1},
    {3, 8, 1},
    {3, 9, 1},
};

static const Mol3DAtom ethyl_acetate_atoms[] = {
    {8, 0.0755f, -0.2491f, -0.0003f},
    {8, 1.5804f, 1.5036f, -0.0001f},
    {6, -1.0138f, 0.6790f, 0.0000f},
    {6, -2.3174f, -0.0906f, 0.0000f},
    {6, 1.3199f, 0.3080f, -0.0002f},
    {6, 2.3545f, -0.7762f, 0.0000f},
    {1, -0.9562f, 1.3095f, 0.8942f},
    {1, -0.9563f, 1.3098f, -0.8941f},
    {1, -3.1733f, 0.5900f, 0.0001f},
    {1, -2.3817f, -0.7396f, -0.8796f},
    {1, -2.3815f, -0.7399f, 0.8793f},
    {1, 2.2490f, -1.3897f, -0.8983f},
    {1, 2.2499f, -1.3884f, 0.8993f},
    {1, 3.3514f, -0.3262f, -0.0008f},
};
static const Mol3DBond ethyl_acetate_bonds[] = {
    {0, 2, 1},
    {0, 4, 1},
    {1, 4, 2},
    {2, 3, 1},
    {2, 6, 1},
    {2, 7, 1},
    {3, 8, 1},
    {3, 9, 1},
    {3, 10, 1},
    {4, 5, 1},
    {5, 11, 1},
    {5, 12, 1},
    {5, 13, 1},
};

static const Mol3DAtom carbon_tetrachloride_atoms[] = {
    {17, 0.7071f, 1.2237f, -1.0849f},
    {17, 1.3068f, -0.9165f, 0.7922f},
    {17, -1.0190f, -1.1147f, -0.9456f},
    {17, -0.9949f, 0.8076f, 1.2378f},
    {6, 0.0000f, -0.0002f, 0.0004f},
};
static const Mol3DBond carbon_tetrachloride_bonds[] = {
    {0, 4, 1},
    {1, 4, 1},
    {2, 4, 1},
    {3, 4, 1},
};

static const Mol3DAtom bromoethane_atoms[] = {
    {35, 2.1840f, 0.3211f, 0.0000f},
    {6, 0.4543f, -0.5673f, 0.0000f},
    {6, -0.6521f, 0.4616f, 0.0000f},
    {1, 0.4198f, -1.1963f, -0.8931f},
    {1, 0.4198f, -1.1963f, 0.8931f},
    {1, -1.6287f, -0.0325f, 0.0000f},
    {1, -0.5984f, 1.1047f, 0.8850f},
    {1, -0.5985f, 1.1047f, -0.8850f},
};
static const Mol3DBond bromoethane_bonds[] = {
    {0, 1, 1},
    {1, 2, 1},
    {1, 3, 1},
    {1, 4, 1},
    {2, 5, 1},
    {2, 6, 1},
    {2, 7, 1},
};

static const Mol3DAtom iodomethane_atoms[] = {
    {53, 1.9257f, 0.0000f, -0.0000f},
    {6, -0.1861f, 0.0000f, -0.0000f},
    {1, -0.5799f, -1.0209f, -0.0000f},
    {1, -0.5800f, 0.5104f, 0.8842f},
    {1, -0.5799f, 0.5105f, -0.8841f},
};
static const Mol3DBond iodomethane_bonds[] = {
    {0, 1, 1},
    {1, 2, 1},
    {1, 3, 1},
    {1, 4, 1},
};

static const Mol3DAtom chloroform_atoms[] = {
    {17, -0.0962f, -1.6789f, 0.4416f},
    {17, -1.4059f, 0.9228f, 0.4416f},
    {17, 1.5022f, 0.7561f, 0.4415f},
    {6, -0.0001f, 0.0000f, -0.1159f},
    {1, -0.0001f, -0.0001f, -1.2089f},
};
static const Mol3DBond chloroform_bonds[] = {
    {0, 3, 1},
    {1, 3, 1},
    {2, 3, 1},
    {3, 4, 1},
};

static const Mol3DAtom chloromethane_atoms[] = {
    {17, 1.6279f, -0.0000f, 0.0000f},
    {6, -0.1393f, -0.0000f, 0.0000f},
    {1, -0.4962f, -0.6985f, 0.7600f},
    {1, -0.4962f, 1.0074f, 0.2249f},
    {1, -0.4963f, -0.3089f, -0.9849f},
};
static const Mol3DBond chloromethane_bonds[] = {
    {0, 1, 1},
    {1, 2, 1},
    {1, 3, 1},
    {1, 4, 1},
};

static const Mol3DAtom diethyl_ether_atoms[] = {
    {8, 0.0008f, -0.3355f, -0.0000f},
    {6, 1.1747f, 0.4629f, -0.0000f},
    {6, -1.1754f, 0.4633f, -0.0000f},
    {6, 2.3873f, -0.4433f, -0.0000f},
    {6, -2.3874f, -0.4437f, -0.0000f},
    {1, 1.1905f, 1.0997f, -0.8916f},
    {1, 1.1905f, 1.0995f, 0.8916f},
    {1, -1.1909f, 1.0997f, 0.8918f},
    {1, -1.1908f, 1.0997f, -0.8918f},
    {1, 3.3119f, 0.1407f, -0.0000f},
    {1, 2.3814f, -1.0955f, 0.8796f},
    {1, 2.3815f, -1.0955f, -0.8796f},
    {1, -3.3125f, 0.1396f, 0.0001f},
    {1, -2.3810f, -1.0959f, -0.8796f},
    {1, -2.3811f, -1.0959f, 0.8796f},
};
static const Mol3DBond diethyl_ether_bonds[] = {
    {0, 1, 1},
    {0, 2, 1},
    {1, 3, 1},
    {1, 5, 1},
    {1, 6, 1},
    {2, 4, 1},
    {2, 7, 1},
    {2, 8, 1},
    {3, 9, 1},
    {3, 10, 1},
    {3, 11, 1},
    {4, 12, 1},
    {4, 13, 1},
    {4, 14, 1},
};

static const Mol3DAtom methoxyethane_atoms[] = {
    {8, -0.5961f, 0.6387f, 0.0000f},
    {6, 0.4226f, -0.3523f, 0.0000f},
    {6, 1.7741f, 0.3297f, 0.0000f},
    {6, -1.8919f, 0.0551f, 0.0000f},
    {1, 0.3267f, -0.9818f, 0.8917f},
    {1, 0.3266f, -0.9818f, -0.8917f},
    {1, 2.5833f, -0.4060f, 0.0000f},
    {1, 1.8815f, 0.9729f, -0.8796f},
    {1, 1.8816f, 0.9730f, 0.8796f},
    {1, -2.0383f, -0.5539f, -0.8974f},
    {1, -2.6320f, 0.8598f, 0.0000f},
    {1, -2.0383f, -0.5539f, 0.8972f},
};
static const Mol3DBond methoxyethane_bonds[] = {
    {0, 1, 1},
    {0, 3, 1},
    {1, 2, 1},
    {1, 4, 1},
    {1, 5, 1},
    {2, 6, 1},
    {2, 7, 1},
    {2, 8, 1},
    {3, 9, 1},
    {3, 10, 1},
    {3, 11, 1},
};

static const Mol3DAtom ethylamine_atoms[] = {
    {7, 1.4364f, -0.2075f, 0.0000f},
    {6, 0.2526f, 0.6429f, 0.0000f},
    {6, -1.0197f, -0.1873f, 0.0000f},
    {1, 0.2743f, 1.2905f, 0.8824f},
    {1, 0.2742f, 1.2905f, -0.8825f},
    {1, -1.0760f, -0.8267f, -0.8874f},
    {1, -1.0760f, -0.8266f, 0.8875f},
    {1, -1.8971f, 0.4673f, 0.0000f},
    {1, 1.4157f, -0.8217f, -0.8134f},
    {1, 1.4157f, -0.8217f, 0.8134f},
};
static const Mol3DBond ethylamine_bonds[] = {
    {0, 1, 1},
    {0, 8, 1},
    {0, 9, 1},
    {1, 2, 1},
    {1, 3, 1},
    {1, 4, 1},
    {2, 5, 1},
    {2, 6, 1},
    {2, 7, 1},
};

static const Mol3DAtom benzene_atoms[] = {
    {6, -1.2131f, -0.6884f, -0.0000f},
    {6, -1.2028f, 0.7064f, 0.0001f},
    {6, -0.0103f, -1.3948f, -0.0000f},
    {6, 0.0104f, 1.3948f, -0.0001f},
    {6, 1.2028f, -0.7063f, -0.0000f},
    {6, 1.2131f, 0.6884f, -0.0000f},
    {1, -2.1577f, -1.2244f, -0.0000f},
    {1, -2.1393f, 1.2564f, 0.0001f},
    {1, -0.0184f, -2.4809f, -0.0001f},
    {1, 0.0184f, 2.4808f, -0.0000f},
    {1, 2.1394f, -1.2563f, 0.0001f},
    {1, 2.1577f, 1.2245f, -0.0000f},
};
static const Mol3DBond benzene_bonds[] = {
    {0, 1, 2},
    {0, 2, 1},
    {0, 6, 1},
    {1, 3, 1},
    {1, 7, 1},
    {2, 4, 2},
    {2, 8, 1},
    {3, 5, 2},
    {3, 9, 1},
    {4, 5, 1},
    {4, 10, 1},
    {5, 11, 1},
};

const Mol3DModel mol3d_models[MOL3D_MODEL_COUNT] = {
    {0U, "ethylene", "C2H4", 6, 5, 1.5361079f, ethylene_atoms, ethylene_bonds},
    {1U, "propylene", "C3H6", 9, 8, 2.3480900f, propylene_atoms, propylene_bonds},
    {2U, "acetylene", "C2H2", 4, 3, 1.6650000f, acetylene_atoms, acetylene_bonds},
    {3U, "propyne", "C3H4", 7, 6, 2.7727000f, propyne_atoms, propyne_bonds},
    {4U, "ethanol", "C2H6O", 9, 8, 1.8636997f, ethanol_atoms, ethanol_bonds},
    {5U, "ethylene_glycol", "C2H6O2", 10, 9, 1.8652938f, ethylene_glycol_atoms, ethylene_glycol_bonds},
    {6U, "glycerol", "C3H8O3", 14, 13, 3.1426890f, glycerol_atoms, glycerol_bonds},
    {7U, "phenol", "C6H6O", 13, 13, 2.9402046f, phenol_atoms, phenol_bonds},
    {8U, "acetic_acid", "C2H4O2", 8, 7, 2.2957083f, acetic_acid_atoms, acetic_acid_bonds},
    {9U, "formaldehyde", "CH2O", 4, 3, 1.2123000f, formaldehyde_atoms, formaldehyde_bonds},
    {10U, "acetaldehyde", "C2H4O", 7, 6, 1.8331923f, acetaldehyde_atoms, acetaldehyde_bonds},
    {11U, "acetone", "C3H6O", 10, 9, 2.1964284f, acetone_atoms, acetone_bonds},
    {12U, "ethyl_acetate", "C4H8O2", 14, 13, 3.3672376f, ethyl_acetate_atoms, ethyl_acetate_bonds},
    {13U, "carbon_tetrachloride", "CCl4", 5, 4, 1.7819313f, carbon_tetrachloride_atoms, carbon_tetrachloride_bonds},
    {14U, "bromoethane", "C2H5Br", 8, 7, 2.2074785f, bromoethane_atoms, bromoethane_bonds},
    {15U, "iodomethane", "CH3I", 5, 4, 1.9257000f, iodomethane_atoms, iodomethane_bonds},
    {16U, "chloroform", "CHCl3", 5, 4, 1.7387393f, chloroform_atoms, chloroform_bonds},
    {17U, "chloromethane", "CH3Cl", 5, 4, 1.6279000f, chloromethane_atoms, chloromethane_bonds},
    {18U, "diethyl_ether", "C4H10O", 15, 14, 3.3154403f, diethyl_ether_atoms, diethyl_ether_bonds},
    {19U, "methoxyethane", "C3H8O", 12, 11, 2.7688770f, methoxyethane_atoms, methoxyethane_bonds},
    {20U, "ethylamine", "C2H7N", 10, 9, 1.9538060f, ethylamine_atoms, ethylamine_bonds},
    {21U, "benzene", "C6H6", 12, 12, 2.4809922f, benzene_atoms, benzene_bonds},
};

const Mol3DModel *mol3d_model_by_class(unsigned class_id)
{
    unsigned i;
    for (i = 0; i < MOL3D_MODEL_COUNT; ++i)
        if (mol3d_models[i].class_id == class_id) return &mol3d_models[i];
    return NULL;
}
