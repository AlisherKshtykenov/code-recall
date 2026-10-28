"""linear через torch.nn.functional."""
import torch.nn.functional as F  # функциональные слои torch


def linear(input, weight, bias=None):
    """y = x·Wᵀ + b — готовая функция torch (в модели — nn.Linear)."""
    return F.linear(input, weight, bias)  # weight (out, in), bias (out,)
