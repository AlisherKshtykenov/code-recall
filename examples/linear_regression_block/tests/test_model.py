import torch

from model import LinearRegression


def line(n=64):
    torch.manual_seed(0)
    X = torch.randn(n, 2)
    return X, X @ torch.tensor([[2.0], [-1.0]]) + 0.5


def test_forward_shape():
    assert LinearRegression(3).forward(torch.randn(7, 3)).shape == (7, 1)


def test_loss_decreases():
    X, y = line()
    losses = LinearRegression(2, lr=0.1).fit(X, y, epochs=50)
    assert losses[-1] < losses[0]


def test_fits_line():
    X, y = line()
    m = LinearRegression(2, lr=0.1)
    m.fit(X, y, epochs=800)
    assert torch.allclose(m.w.detach().flatten(), torch.tensor([2.0, -1.0]), atol=0.15)
