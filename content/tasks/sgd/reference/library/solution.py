"""sgd через torch.optim."""
import torch  # torch.optim — готовые оптимизаторы


class SGD(torch.optim.SGD):
    """Готовый SGD: SGD(model.parameters(), lr=0.01, momentum=0.9, nesterov=False, weight_decay=0)."""


optimizer = SGD  # реализация слота optimizer
