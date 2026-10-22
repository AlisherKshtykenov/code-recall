"""dropout своими руками — как torch.nn.functional.dropout: в обучении обнуляем каждый элемент с вероятностью p,
выжившие умножаем на 1 / (1 − p), чтобы среднее не менялось; в инференсе — ничего не делаем."""
import torch


def dropout(input, p=0.5, training=True, inplace=False):
    """Случайная маска: элемент остаётся с вероятностью 1 − p (и масштабируется), иначе становится 0."""
    if p < 0.0 or p > 1.0:
        raise ValueError(f"dropout probability has to be between 0 and 1, but got {p}")
    if not training or p == 0.0:
        return input  # инференс или p = 0: тот же тензор, как в torch
    if p == 1.0:
        return input.mul_(0) if inplace else input * 0  # всё обнуляется (без деления на 0)
    keep = torch.rand_like(input) >= p  # True с вероятностью 1 − p; генератор — общий torch (seed: torch.manual_seed)
    scale = 1.0 / (1.0 - p)  # «inverted dropout»: масштаб в обучении, чтобы в инференсе ничего не делать
    if inplace:
        return input.mul_(keep).mul_(scale)
    return input * keep * scale
