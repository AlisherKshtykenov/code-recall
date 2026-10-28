"""log_loss через torch и sklearn."""
import torch.nn.functional as F  # потери torch

from sklearn import metrics  # метрики sklearn


def binary_cross_entropy(input, target, weight=None, reduction="mean"):
    """BCE по вероятностям — для обучения (input в [0, 1], target той же формы и dtype)."""
    return F.binary_cross_entropy(input, target, weight=weight, reduction=reduction)  # log обрезан на −100


def log_loss(y_true, y_proba=None, *, normalize=True, sample_weight=None, labels=None):
    """Логистическая потеря как метрика на валидации (numpy, бинарная и многоклассовая)."""
    return metrics.log_loss(  # −среднее log P(настоящего класса)
        y_true, y_proba,  # метки и вероятности (n,) или (n, n_classes)
        normalize=normalize,  # среднее (True) или сумма
        sample_weight=sample_weight,  # веса объектов
        labels=labels,  # все классы — нужно, если в y_true только один
    )


loss = binary_cross_entropy  # реализация слота loss
