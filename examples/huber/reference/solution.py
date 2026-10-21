import torch


def loss(y_pred, y, delta=1.0):
    """Huber: квадрат для маленьких ошибок, модуль — для больших (устойчив к выбросам)."""
    err = (y_pred - y).abs()
    quad = 0.5 * err ** 2
    lin = delta * (err - 0.5 * delta)
    return torch.where(err <= delta, quad, lin).mean()
