"""log_loss (логистическая потеря, бинарная кросс-энтропия) своими руками:
binary_cross_entropy — как torch.nn.functional.binary_cross_entropy (значения и градиенты, в т.ч. на краях),
log_loss — как sklearn.metrics.log_loss (метрика по вероятностям, бинарная и многоклассовая)."""
import warnings

import numpy as np
import torch

REDUCTIONS = ("none", "mean", "sum")


class _BCE(torch.autograd.Function):
    """Поэлементная BCE с градиентом по формуле torch: (p − t) / max(p(1 − p), 1e−12).
    Обычный autograd от формулы с clamp дал бы на краях (p = 0 или 1) градиент 0, а torch — ±1e12."""

    @staticmethod
    def forward(ctx, p, t, weight):
        log_p = torch.clamp(torch.log(p), min=-100)  # log(0) = −inf -> −100, как в torch
        log_1mp = torch.clamp(torch.log1p(-p), min=-100)  # log(1 − p) точнее через log1p
        loss = -(t * log_p + (1 - t) * log_1mp)  # −[t·log p + (1 − t)·log(1 − p)]
        if weight is not None:
            loss = loss * weight  # вес каждого элемента (или канала — через broadcast)
        ctx.save_for_backward(p, t, weight)
        return loss

    @staticmethod
    def backward(ctx, grad_out):
        p, t, weight = ctx.saved_tensors
        grad = grad_out * (p - t) / torch.clamp(p * (1 - p), min=1e-12)  # d loss / d p
        if weight is not None:
            grad = grad * weight
        return grad, None, None  # по target и weight градиент не считаем


def binary_cross_entropy(input, target, weight=None, reduction="mean"):
    """BCE по вероятностям input ∈ [0, 1] и ответам target той же формы."""
    if reduction not in REDUCTIONS:
        raise ValueError(f"{reduction} is not a valid value for reduction")
    if target.shape != input.shape:  # torch не угадывает broadcast для потерь
        raise ValueError(f"Using a target size ({target.shape}) that is different to the input size ({input.shape}) is deprecated. "
                         "Please ensure they have the same size.")
    if target.dtype != input.dtype:  # long-метки сначала .float()
        raise RuntimeError(f"Found dtype {str(target.dtype).split('.')[-1].capitalize()} but expected {str(input.dtype).split('.')[-1].capitalize()}")
    if input.numel() and ((input < 0) | (input > 1)).any():  # это вероятности (для логитов — weighted_cross_entropy)
        raise RuntimeError("all elements of input should be between 0 and 1")
    if weight is not None:
        weight = torch.broadcast_to(weight, input.shape).to(input.dtype)  # вес на каждый элемент
    loss = _BCE.apply(input, target, weight)
    if reduction == "none":
        return loss
    return loss.sum() if reduction == "sum" else loss.mean()  # mean пустого тензора — nan, как в torch


def log_loss(y_true, y_proba=None, *, normalize=True, sample_weight=None, labels=None):
    """Средняя −log(вероятности настоящего класса). y_proba — вероятность класса 1 (бинарная) или (n, n_classes)."""
    y_true = np.asarray(y_true)
    y_proba = np.asarray(y_proba)
    if len(y_true) == 0:
        raise ValueError("Found array with 0 sample(s) (shape=(0,)) while a minimum of 1 is required.")
    if len(y_true) != len(y_proba):
        raise ValueError(f"Found input variables with inconsistent numbers of samples: [{len(y_proba)}, {len(y_true)}]")
    if not np.issubdtype(y_proba.dtype, np.floating):
        y_proba = y_proba.astype(np.float64)  # целые 0/1 -> float
    if (y_proba > 1).any():
        raise ValueError(f"y_prob contains values greater than 1: {y_proba.max()}")
    if (y_proba < 0).any():
        raise ValueError(f"y_prob contains values less than 0: {y_proba.min()}")

    classes = np.unique(y_true) if labels is None else np.unique(labels)  # столбцы вероятностей — классы по возрастанию
    if len(classes) == 1:
        raise ValueError(f"y_true contains only one label ({classes[0]}). Please provide the list of all expected class labels "
                         "explicitly through the labels argument.")
    if y_proba.ndim == 1:
        y_proba = y_proba[:, None]
    if y_proba.shape[1] == 1:
        y_proba = np.hstack([1 - y_proba, y_proba])  # бинарная: [P(класс 0), P(класс 1)]
    if y_proba.shape[1] != len(classes):
        if labels is None:
            raise ValueError(f"y_true and y_prob contain different number of classes: {len(classes)} vs {y_proba.shape[1]}. "
                             "Please provide the true labels explicitly through the labels argument.")
        raise ValueError(f"The number of classes in labels is different from that in y_prob. Classes found in labels: {classes}")
    if not np.isin(y_true, classes).all():
        raise ValueError("y_true contains values not belonging to the passed labels")

    eps = np.finfo(y_proba.dtype).eps  # обрезка — машинным эпсилоном того же dtype (float32 и float64 различаются)
    y_proba = np.clip(y_proba, eps, 1 - eps)  # log(0) = −inf -> конечное большое число
    rows = y_proba.sum(axis=1)
    if not np.allclose(rows, 1, rtol=np.sqrt(eps)):  # не перенормируем — только предупреждаем, как sklearn
        warnings.warn("The y_prob values do not sum to one. Make sure to pass probabilities.", UserWarning, stacklevel=2)
    onehot = (y_true[:, None] == classes[None, :]).astype(np.float64)  # 1 в столбце настоящего класса
    per_sample = -(onehot * np.log(y_proba)).sum(axis=1)  # −log P(настоящий класс)
    w = np.ones(len(y_true)) if sample_weight is None else np.asarray(sample_weight, dtype=np.float64)
    return float(np.average(per_sample, weights=w)) if normalize else float(np.sum(per_sample * w))


loss = binary_cross_entropy  # реализация слота loss: loss(y_pred, y_true)
