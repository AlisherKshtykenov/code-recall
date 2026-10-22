"""Контракт слота activation — верен для любой реализации (relu, sigmoid, tanh, gelu…)."""
import torch

from slots.activation import activation


def test_same_shape_and_dtype():
    for shape in [(5,), (2, 3), (2, 3, 4, 4)]:
        x = torch.randn(shape)
        y = activation(x)
        assert y.shape == x.shape and y.dtype == x.dtype, f"форма и dtype должны сохраниться: {tuple(x.shape)}"


def test_elementwise():
    x = torch.randn(10)
    y = activation(x)
    assert torch.allclose(activation(x[3:4]), y[3:4]), "значение в точке не зависит от соседей (поэлементно)"


def test_differentiable():
    x = torch.randn(8, requires_grad=True)
    activation(x).sum().backward()
    assert x.grad is not None and torch.isfinite(x.grad).all(), "градиент существует и конечен"


def test_monotone_non_decreasing():
    x = torch.linspace(-5, 5, 101)
    y = activation(x)
    assert (y[1:] >= y[:-1] - 1e-6).all(), "активация не убывает"


def test_does_not_change_input():
    x = torch.randn(6)
    before = x.clone()
    activation(x)
    assert torch.equal(x, before), "вход не меняется"
