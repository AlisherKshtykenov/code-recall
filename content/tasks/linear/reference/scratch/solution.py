"""linear своими руками — как torch.nn.functional.linear: y = x·Wᵀ + b (полносвязный слой, dense)."""
import torch


def linear(input, weight, bias=None):
    """input (*, in_features), weight (out_features, in_features), bias (out_features,) -> (*, out_features).
    weight может быть и одномерным (in_features,) — тогда выход без последней оси."""
    if weight.dim() == 1 and bias is not None:  # так ведёт себя torch: одномерный weight — только без bias
        raise RuntimeError("mat2 must be a matrix, got 1-D tensor")
    out = torch.matmul(input, weight.t() if weight.dim() == 2 else weight)  # x·Wᵀ: каждая строка x умножается на каждый нейрон
    if bias is not None:
        out = out + bias  # сдвиг каждого выхода (broadcast по всем осям, кроме последней)
    return out
