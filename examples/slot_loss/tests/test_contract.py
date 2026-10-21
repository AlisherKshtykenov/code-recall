"""Контракт слота loss — верен для любой реализации (MSE, MAE, Huber…)."""
import torch

from slots.loss import loss


def test_scalar():
    out = loss(torch.randn(8, 1), torch.randn(8, 1))
    assert out.dim() == 0, f"нужен скаляр, а форма {tuple(out.shape)}"


def test_zero_when_equal():
    y = torch.randn(5, 1)
    assert loss(y, y.clone()).item() == 0


def test_non_negative():
    torch.manual_seed(0)
    for _ in range(5):
        assert loss(torch.randn(10, 1), torch.randn(10, 1)).item() >= 0


def test_grows_with_error():
    y = torch.zeros(4, 1)
    assert loss(y + 3, y) > loss(y + 1, y)


def test_differentiable():
    p = torch.randn(6, 1, requires_grad=True)
    loss(p, torch.randn(6, 1)).backward()
    assert p.grad is not None and p.grad.abs().sum() > 0
