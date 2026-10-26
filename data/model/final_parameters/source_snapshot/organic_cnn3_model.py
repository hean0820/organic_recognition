"""7020紧凑三层候选；保留旧两层类及其检查点的兼容性。"""
from torch import nn
from organic_torch_model import OrganicCNN, CONFUSION_GROUPS


class OrganicCNN3(OrganicCNN):
    def __init__(self, num_classes=22, channels=(16, 32, 48)):
        # 复用旧模型的辅助头融合语义，只替换特征与嵌入结构。
        nn.Module.__init__(self)
        blocks = []
        in_channels = 1
        if len(channels) != 3 or channels[-1] != 48:
            raise ValueError('Three conv layers ending in 48 channels are required by FC3072/48/22')
        for out_channels in channels:
            blocks.extend([
                nn.Conv2d(in_channels, out_channels, 3, padding=1),
                nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            ])
            in_channels = out_channels
        self.features = nn.Sequential(*blocks)
        self.embedding = nn.Sequential(
            nn.Flatten(), nn.Linear(48 * 8 * 8, 48), nn.ReLU(inplace=True), nn.Dropout(0.25),
        )
        self.classifier = nn.Linear(48, num_classes)
        self.group_heads = nn.ModuleDict({
            name: nn.Linear(48, len(indices)) for name, indices in CONFUSION_GROUPS.items()
        })


class OrganicCNN3Wide(OrganicCNN3):
    """已做静态资源预算的24/48/48备选；不表示已通过PL实现。"""
    def __init__(self, num_classes=22):
        super().__init__(num_classes, channels=(24, 48, 48))
