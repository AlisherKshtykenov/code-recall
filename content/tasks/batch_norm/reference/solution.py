"""batch_norm своими руками — как torch.nn.functional.batch_norm: обучение (статистики батча + обновление
running_mean/running_var) и инференс (накопленные статистики)."""
import torch


def batch_norm(input, running_mean, running_var, weight=None, bias=None, training=False, momentum=0.1, eps=1e-5):
    """Каждый канал: (x − mean) / √(var + eps) · weight + bias. Канал — ось 1: (N, C), (N, C, L), (N, C, H, W)…"""
    if input.dim() < 2:
        raise RuntimeError(f"running_mean should contain {input.shape[1] if input.dim() > 1 else 0} elements not "
                           f"{running_mean.numel() if running_mean is not None else 0}")
    C = input.shape[1]
    for name, t in (("running_mean", running_mean), ("running_var", running_var)):
        if t is not None and t.numel() != C:
            raise RuntimeError(f"{name} should contain {C} elements not {t.numel()}")
    dims = [0] + list(range(2, input.dim()))  # по всем осям, кроме каналов: батч и пиксели
    shape = [1, C] + [1] * (input.dim() - 2)  # (C,) -> (1, C, 1, 1): broadcast на каждый пиксель канала

    if training:
        n = input.numel() // C  # сколько значений в канале
        if n <= 1:
            raise ValueError(f"Expected more than 1 value per channel when training, got input size {input.size()}")
        mean = input.mean(dim=dims)  # среднее канала по батчу и пикселям
        var = ((input - mean.view(shape)) ** 2).mean(dim=dims)  # дисперсия со смещением (делим на n) — для нормировки
        with torch.no_grad():  # накопленные статистики не участвуют в градиенте
            if running_mean is not None:
                running_mean.mul_(1 - momentum).add_(mean.detach(), alpha=momentum)  # rm = (1 − m)·rm + m·mean
            if running_var is not None:
                running_var.mul_(1 - momentum).add_(var.detach() * n / (n - 1), alpha=momentum)  # в running — несмещённая
    else:
        if running_mean is None or running_var is None:
            raise RuntimeError("running_mean must be defined in evaluation mode")
        mean, var = running_mean, running_var  # инференс: статистики, накопленные при обучении

    out = (input - mean.view(shape)) / torch.sqrt(var.view(shape) + eps)  # нормировка: среднее 0, дисперсия 1
    if weight is not None:
        out = out * weight.view(shape)  # обучаемый масштаб γ
    if bias is not None:
        out = out + bias.view(shape)  # обучаемый сдвиг β
    return out
