"""weighted_cross_entropy своими руками — как torch.nn.functional.binary_cross_entropy_with_logits(…, pos_weight):
BCE прямо по логитам (sigmoid внутри, численно устойчиво) с весом положительного класса."""
import torch

REDUCTIONS = ("none", "mean", "sum")


def _softplus_neg(x):
    """log(1 + e^(−x)) = −log σ(x) без переполнения:
    x ≥ 0: log1p(e^(−x));  x < 0: −x + log1p(e^x). Экспонента — всегда от неположительного числа.
    −|x| пишем через where, а не abs: у abs в нуле градиент 0, и производная в нуле получилась бы неверной."""
    m = torch.where(x >= 0, -x, x)  # −|x| с правильным градиентом
    return torch.log1p(torch.exp(m)) + torch.where(x >= 0, torch.zeros_like(x), -x)


def binary_cross_entropy_with_logits(input, target, weight=None, reduction="mean", pos_weight=None):
    """loss = −[pos_weight·t·log σ(x) + (1 − t)·log(1 − σ(x))] по логитам x."""
    if reduction not in REDUCTIONS:
        raise ValueError(f"{reduction} is not a valid value for reduction")
    if target.shape != input.shape:  # torch не угадывает broadcast для потерь
        raise ValueError(f"Target size ({target.shape}) must be the same as input size ({input.shape})")
    # log(1 − σ(x)) = −x − softplus(−x)... удобнее так: (1 − t)·x + (1 + (pw − 1)·t)·softplus(−x)
    sp = _softplus_neg(input)  # −log σ(x)
    if pos_weight is None:
        loss = (1 - target) * input + sp  # −t·log σ(x) − (1 − t)·log(1 − σ(x)), т.к. −log(1 − σ(x)) = x + softplus(−x)
    else:
        log_weight = 1 + (pos_weight - 1) * target  # для положительных — pos_weight, для отрицательных — 1
        loss = (1 - target) * input + log_weight * sp
    if weight is not None:
        loss = loss * weight  # вес элемента (broadcast)
    if reduction == "none":
        return loss
    return loss.sum() if reduction == "sum" else loss.mean()


loss = binary_cross_entropy_with_logits  # реализация слота loss: loss(y_pred, y_true), y_pred — логиты
