"""baseline_cnn через torch: conv_block × N -> torch.flatten -> F.dropout -> F.linear."""
import math  # для инициализации

import torch  # тензоры
import torch.nn.functional as F  # готовые функциональные слои
from torch import nn  # nn.Module, nn.ModuleList, nn.Parameter

from bricks.conv_block import ConvBlock  # свой блок (кирпичик)


class BaselineCNN(nn.Module):
    """(N, in_channels, image_size, image_size) -> (N, 1) логитов."""

    def __init__(self, in_channels=1, channels=(16, 32, 64), image_size=64, dropout=0.5):
        super().__init__()
        self.p = dropout  # вероятность dropout перед последним слоем
        sizes = [in_channels, *channels]
        self.blocks = nn.ModuleList(ConvBlock(a, b) for a, b in zip(sizes, sizes[1:]))  # каждый блок — карта вдвое меньше
        side = image_size // 2 ** len(channels)  # сторона карты после всех блоков
        if side < 1:
            raise ValueError(f"картинка {image_size}×{image_size} слишком мала для {len(channels)} блоков")
        self.features = channels[-1] * side * side  # длина вектора признаков
        self.fc_weight = nn.Parameter(torch.empty(1, self.features))  # последний слой: признаки -> 1 логит
        self.fc_bias = nn.Parameter(torch.empty(1))
        nn.init.kaiming_uniform_(self.fc_weight, a=math.sqrt(5))  # как у nn.Linear
        nn.init.uniform_(self.fc_bias, -1 / math.sqrt(self.features), 1 / math.sqrt(self.features))

    def forward(self, x):
        for block in self.blocks:
            x = block(x)  # conv -> bn -> relu -> pool
        x = torch.flatten(x, 1)  # (N, C, h, w) -> (N, C·h·w)
        x = F.dropout(x, self.p, training=self.training)  # только в обучении
        return F.linear(x, self.fc_weight, self.fc_bias)  # (N, 1) — логит брака
