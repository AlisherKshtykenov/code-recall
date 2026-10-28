"""baseline_cnn — простая свёрточная сеть для «брак / норма» на своих кирпичиках:
conv_block × N -> flatten -> dropout -> linear -> 1 логит (вероятность брака = sigmoid(логит))."""
import math

import torch
from torch import nn

from bricks.conv_block import ConvBlock
from bricks.dropout import dropout
from bricks.flatten import flatten
from bricks.linear import linear


class BaselineCNN(nn.Module):
    """(N, in_channels, image_size, image_size) -> (N, 1) логитов."""

    def __init__(self, in_channels=1, channels=(16, 32, 64), image_size=64, dropout=0.5):
        super().__init__()
        self.p = dropout  # вероятность dropout перед последним слоем
        sizes = [in_channels, *channels]
        self.blocks = nn.ModuleList(ConvBlock(a, b) for a, b in zip(sizes, sizes[1:]))  # каждый блок — карта вдвое меньше
        side = image_size // 2 ** len(channels)  # сторона карты после всех блоков (64 -> 32 -> 16 -> 8)
        if side < 1:
            raise ValueError(f"картинка {image_size}×{image_size} слишком мала для {len(channels)} блоков")
        self.features = channels[-1] * side * side  # длина вектора признаков после flatten
        self.fc_weight = nn.Parameter(torch.empty(1, self.features))  # последний слой: признаки -> 1 логит
        self.fc_bias = nn.Parameter(torch.empty(1))
        bound = 1 / math.sqrt(self.features)  # инициализация как у nn.Linear
        nn.init.kaiming_uniform_(self.fc_weight, a=math.sqrt(5))
        nn.init.uniform_(self.fc_bias, -bound, bound)

    def forward(self, x):
        for block in self.blocks:
            x = block(x)  # conv -> bn -> relu -> pool
        x = flatten(x, 1)  # (N, C, h, w) -> (N, C·h·w)
        x = dropout(x, self.p, training=self.training)  # только в обучении
        return linear(x, self.fc_weight, self.fc_bias)  # (N, 1) — логит брака
