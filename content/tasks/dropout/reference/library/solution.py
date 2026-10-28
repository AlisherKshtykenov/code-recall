"""dropout через torch.nn.functional."""
import torch.nn.functional as F  # функциональные слои torch


def dropout(input, p=0.5, training=True, inplace=False):
    """Случайно обнулить долю p (в обучении); в модели передавайте training=self.training."""
    return F.dropout(input, p=p, training=training, inplace=inplace)  # выжившие × 1/(1 − p)
