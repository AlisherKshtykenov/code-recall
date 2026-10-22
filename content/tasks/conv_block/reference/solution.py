"""conv_block — блок свёрточной сети на своих кирпичиках: conv2d -> batch_norm -> relu -> max_pool2d.
nn.Module хранит веса (Parameter) и running-статистики (buffer), а считает всё — мои функции."""
import math

import torch
from torch import nn

from bricks.batch_norm import batch_norm
from bricks.conv2d import conv2d
from bricks.max_pool2d import max_pool2d
from bricks.relu import relu


class ConvBlock(nn.Module):
    """(N, C_in, H, W) -> (N, C_out, H/pool, W/pool): ищет узоры, нормирует, оставляет положительное, уменьшает карту."""

    def __init__(self, in_channels, out_channels, kernel_size=3, padding=1, pool=2, momentum=0.1, eps=1e-5):
        super().__init__()
        self.padding, self.pool, self.momentum, self.eps = padding, pool, momentum, eps
        self.weight = nn.Parameter(torch.empty(out_channels, in_channels, kernel_size, kernel_size))  # ядра свёртки
        self.bias = nn.Parameter(torch.empty(out_channels))  # сдвиг свёртки
        self.bn_weight = nn.Parameter(torch.ones(out_channels))  # γ batch_norm
        self.bn_bias = nn.Parameter(torch.zeros(out_channels))  # β batch_norm
        self.register_buffer("running_mean", torch.zeros(out_channels))  # накопленные статистики — не обучаются,
        self.register_buffer("running_var", torch.ones(out_channels))  # но сохраняются в state_dict и едут на device
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))  # та же инициализация, что у nn.Conv2d
        bound = 1 / math.sqrt(in_channels * kernel_size * kernel_size)
        nn.init.uniform_(self.bias, -bound, bound)

    def forward(self, x):
        x = conv2d(x, self.weight, self.bias, padding=self.padding)  # свёртка: карты признаков
        x = batch_norm(x, self.running_mean, self.running_var, self.bn_weight, self.bn_bias,
                       training=self.training, momentum=self.momentum, eps=self.eps)  # train/eval — от model.train()/eval()
        x = relu(x)  # нелинейность
        return max_pool2d(x, self.pool)  # карта вдвое меньше
