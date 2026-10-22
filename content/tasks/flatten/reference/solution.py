"""flatten своими руками — как torch.flatten: склеить оси с start_dim по end_dim в одну."""
import math

import torch


def _dim(d, ndim, name):
    """Отрицательную ось -> положительную; вне диапазона — IndexError, как в torch."""
    lo, hi = -max(ndim, 1), max(ndim, 1) - 1  # у 0-мерного тензора допустимы оси 0 и −1
    if not lo <= d <= hi:
        raise IndexError(f"Dimension out of range (expected to be in range of [{lo}, {hi}], but got {d})")
    return d % max(ndim, 1)


def flatten(input, start_dim=0, end_dim=-1):
    """(…, a, b, c, …) -> (…, a·b·c, …): оси start_dim…end_dim включительно становятся одной."""
    if not isinstance(input, torch.Tensor):
        raise TypeError(f"flatten(): argument 'input' must be Tensor, not {type(input).__name__}")
    s, e = _dim(start_dim, input.dim(), "start_dim"), _dim(end_dim, input.dim(), "end_dim")
    if s > e:
        raise RuntimeError("flatten() has invalid args: start_dim cannot come after end_dim")
    if input.dim() == 0:
        return input.reshape(1)  # скаляр -> вектор из одного элемента
    if s == e:
        return input  # склеивать нечего — torch возвращает тот же тензор
    shape = list(input.shape)
    new_shape = shape[:s] + [math.prod(shape[s:e + 1])] + shape[e + 1:]  # произведение размеров склеиваемых осей
    return input.reshape(new_shape)  # данные не копируются, если можно (view)
