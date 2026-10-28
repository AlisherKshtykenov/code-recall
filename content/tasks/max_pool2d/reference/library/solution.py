"""max_pool2d через torch.nn.functional."""
import torch.nn.functional as F  # функциональные слои torch


def max_pool2d(input, kernel_size, stride=None, padding=0, dilation=1, ceil_mode=False, return_indices=False):
    """Максимум каждого окна — готовая функция torch (в модели — nn.MaxPool2d)."""
    return F.max_pool2d(input, kernel_size, stride=stride, padding=padding, dilation=dilation,  # окно, шаг, отступ
                        ceil_mode=ceil_mode, return_indices=return_indices)  # округление размера, индексы максимумов
