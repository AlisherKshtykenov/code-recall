"""conv_block через torch.nn.functional: conv2d -> batch_norm -> relu -> max_pool2d."""
import math  # для инициализации

import torch  # тензоры и параметры
import torch.nn.functional as F  # готовые функциональные слои
from torch import nn  # nn.Module, nn.Parameter, nn.init


class ConvBlock(nn.Module):
    """Те же веса, что у nn.Conv2d + nn.BatchNorm2d; считают готовые функции torch."""

    def __init__(self, in_channels, out_channels, kernel_size=3, padding=1, pool=2, momentum=0.1, eps=1e-5):
        super().__init__()
        self.padding, self.pool, self.momentum, self.eps = padding, pool, momentum, eps  # настройки блока
        self.weight = nn.Parameter(torch.empty(out_channels, in_channels, kernel_size, kernel_size))  # ядра свёртки
        self.bias = nn.Parameter(torch.empty(out_channels))  # сдвиг свёртки
        self.bn_weight = nn.Parameter(torch.ones(out_channels))  # γ batch_norm
        self.bn_bias = nn.Parameter(torch.zeros(out_channels))  # β batch_norm
        self.register_buffer("running_mean", torch.zeros(out_channels))  # статистики — буферы (в state_dict, не в оптимизатор)
        self.register_buffer("running_var", torch.ones(out_channels))
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))  # инициализация как у nn.Conv2d
        bound = 1 / math.sqrt(in_channels * kernel_size * kernel_size)
        nn.init.uniform_(self.bias, -bound, bound)

    def forward(self, x):
        x = F.conv2d(x, self.weight, self.bias, padding=self.padding)  # свёртка
        x = F.batch_norm(x, self.running_mean, self.running_var, self.bn_weight, self.bn_bias,
                         training=self.training, momentum=self.momentum, eps=self.eps)  # train/eval — из модуля
        x = F.relu(x)  # нелинейность
        return F.max_pool2d(x, self.pool)  # карта вдвое меньше
