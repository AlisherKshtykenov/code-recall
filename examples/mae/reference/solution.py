import torch


def loss(y_pred, y):
    """MAE — реализация слота loss."""
    return (y_pred - y).abs().mean()
