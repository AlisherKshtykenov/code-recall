"""flatten через torch."""
import torch  # тензоры


def flatten(input, start_dim=0, end_dim=-1):
    """Склеить оси start_dim…end_dim — готовая функция torch (в модели — nn.Flatten(), у неё start_dim=1)."""
    return torch.flatten(input, start_dim, end_dim)  # view, если можно (без копии)
