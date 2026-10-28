"""conv2d через torch.nn.functional."""
import torch.nn.functional as F  # функциональные слои torch


def conv2d(input, weight, bias=None, stride=1, padding=0, dilation=1, groups=1):
    """Свёртка — готовая функция torch (в модели — слой nn.Conv2d)."""
    return F.conv2d(input, weight, bias, stride=stride, padding=padding, dilation=dilation, groups=groups)  # все настройки — явно
