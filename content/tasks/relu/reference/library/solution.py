"""relu через torch."""
import torch  # тензоры и готовые функции


def relu(input):
    """max(0, x) поэлементно — готовая функция torch (градиент в нуле — 0)."""
    return torch.relu(input)  # для слоя в nn.Sequential — nn.ReLU()


activation = relu  # реализация слота activation
