"""batch_norm через torch.nn.functional."""
import torch.nn.functional as F  # функциональные слои torch


def batch_norm(input, running_mean, running_var, weight=None, bias=None, training=False, momentum=0.1, eps=1e-5):
    """Нормировка каналов по батчу (train) или по накопленным статистикам (eval) — в модели это nn.BatchNorm2d."""
    return F.batch_norm(input, running_mean, running_var, weight, bias,  # вход, статистики, γ и β
                        training=training, momentum=momentum, eps=eps)  # режим, доля нового батча, добавка под корень
