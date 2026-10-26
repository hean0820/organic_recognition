import torch
from torch import nn

# 容易互相混淆的类别分组。辅助分类头会专门学习组内差异。
CONFUSION_GROUPS = {
    "hydrocarbon": [0, 1, 2, 3],
    "alcohol_ether": [4, 5, 6, 18, 19],
    "carbonyl_ester": [8, 9, 10, 11, 12],
    "halogen": [13, 14, 15, 16, 17],
    "aromatic": [7, 21],
}
AUXILIARY_WEIGHT = 0.35  # 辅助分类结果融合到主分类结果时的权重


class OrganicCNN(nn.Module):
    """面向 64x64 灰度手写有机物图片的卷积分类网络。

    结构说明（2026-10-04 变更）：原三层卷积的第三层 Conv3/BN3/Pool3 已被移除，
    当前只保留 Conv1 和 Conv2 两层卷积。两次 2x2 池化后特征图为 48x16x16，
    因此 FC1 的输入维度由 96*8*8=6144 变为 48*16*16=12288。

    FC1 输出维度同步从 96 降为 48，理由是让 FC1 权重占用回到 result_6 的水平：
    12288*48=589824 字节，与三层版 6144*96 完全一致，减小 PL 端 BRAM/DDR 压力。

    重要版本提示：本结构的 state_dict 与旧三层模型不兼容。旧三层模型的权重
    只能通过 git 历史或备份的 .pt 恢复，不能直接 load_state_dict 到当前类。
    """
    def __init__(self, num_classes=22):
        super().__init__()
        # 两次卷积和池化后，特征图尺寸由 64x64 缩小为 16x16，通道为 48。
        # 第三个 Conv3 + BN3 + ReLU + MaxPool 已按需求移除。
        self.features = nn.Sequential(
            nn.Conv2d(1, 24, 3, padding=1),
            nn.BatchNorm2d(24), nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(24, 48, 3, padding=1),
            nn.BatchNorm2d(48), nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        # 将卷积特征压缩为 48 维特征向量，并使用 Dropout 抑制过拟合。
        # FC1 输入维度 = 48 * 16 * 16 = 12288，输出维度 = 48。
        self.embedding = nn.Sequential(
            nn.Flatten(),
            nn.Linear(48 * 16 * 16, 48), nn.ReLU(inplace=True),
            nn.Dropout(0.25),
        )
        self.classifier = nn.Linear(48, num_classes)
        # 每个易混淆分组使用一个独立的辅助分类头。
        self.group_heads = nn.ModuleDict({
            name: nn.Linear(48, len(indices)) for name, indices in CONFUSION_GROUPS.items()
        })

    def forward(self, x, return_aux=False):
        """默认返回融合后的 22 类 logits；训练时可同时返回辅助分类结果。"""
        feature = self.embedding(self.features(x))
        logits = self.classifier(feature)
        auxiliary = {name: head(feature) for name, head in self.group_heads.items()}
        fused = logits.clone()
        for name, indices in CONFUSION_GROUPS.items():
            fused[:, indices] = fused[:, indices] + AUXILIARY_WEIGHT * auxiliary[name]
        return (fused, auxiliary) if return_aux else fused
