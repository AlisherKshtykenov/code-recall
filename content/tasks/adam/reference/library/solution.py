"""adam через torch.optim."""
import torch  # torch.optim — готовые оптимизаторы


class Adam(torch.optim.Adam):
    """Готовый Adam: Adam(model.parameters(), lr=1e-3, betas=(0.9, 0.999), weight_decay=0, amsgrad=False)."""


optimizer = Adam  # реализация слота optimizer
