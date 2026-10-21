import torch

from slots.loss import loss


class LinearRegression:
    """Линейная регрессия на torch с нуля: веса, прямой проход, шаг градиентного спуска.
    Функция потерь — из слота loss (MSE, MAE, Huber…)."""

    def __init__(self, n_features, lr=0.05):
        self.w = torch.zeros(n_features, 1, requires_grad=True)
        self.b = torch.zeros(1, requires_grad=True)
        self.lr = lr

    def forward(self, X):
        return X @ self.w + self.b

    def step(self, X, y):
        value = loss(self.forward(X), y)
        value.backward()
        with torch.no_grad():
            for p in (self.w, self.b):
                p -= self.lr * p.grad
                p.grad.zero_()
        return value.item()

    def fit(self, X, y, epochs=300):
        return [self.step(X, y) for _ in range(epochs)]

    def predict(self, X):
        with torch.no_grad():
            return self.forward(X)
