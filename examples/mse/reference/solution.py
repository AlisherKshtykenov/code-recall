import torch


def loss(y_pred, y):
    """MSE — реализация слота loss."""
    return ((y_pred - y) ** 2).mean()
