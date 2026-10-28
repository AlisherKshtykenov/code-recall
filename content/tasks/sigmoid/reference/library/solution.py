"""sigmoid через torch."""
import torch  # тензоры и готовые функции


def sigmoid(input):
    """1 / (1 + e^(−x)) — torch считает устойчиво при любых x."""
    return torch.sigmoid(input)  # в обучении вместо sigmoid + BCELoss берут BCEWithLogitsLoss


activation = sigmoid  # реализация слота activation
