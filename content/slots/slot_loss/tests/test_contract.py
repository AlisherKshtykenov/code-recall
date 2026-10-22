"""Контракт слота loss — верен для любой реализации (log_loss, weighted_cross_entropy, mse, mae…).
y_pred берём в (0, 1): это допустимые и вероятности, и логиты, и числа."""
import torch

from slots.loss import loss

Y_TRUE = torch.tensor([1.0, 0.0, 1.0, 1.0, 0.0])


def test_scalar():
    out = loss(torch.full((5,), 0.5), Y_TRUE)
    assert out.dim() == 0, f"нужен скаляр, а форма {tuple(out.shape)}"


def test_non_negative():
    torch.manual_seed(0)
    for _ in range(5):
        assert loss(torch.rand(5) * 0.98 + 0.01, Y_TRUE).item() >= 0, "потери не бывают отрицательными"


def test_better_prediction_lower_loss():
    good = torch.where(Y_TRUE == 1, torch.tensor(0.9), torch.tensor(0.1))
    bad = torch.where(Y_TRUE == 1, torch.tensor(0.1), torch.tensor(0.9))
    assert loss(good, Y_TRUE) < loss(bad, Y_TRUE), "предсказание ближе к ответу — потери меньше"


def test_differentiable():
    p = (torch.rand(5) * 0.98 + 0.01).requires_grad_()
    loss(p, Y_TRUE).backward()
    assert p.grad is not None and torch.isfinite(p.grad).all() and p.grad.abs().sum() > 0, "градиент по y_pred существует, конечен и не нулевой"


def test_works_on_batch_shapes():
    p, t = torch.rand(4, 1) * 0.98 + 0.01, torch.randint(0, 2, (4, 1)).float()
    assert loss(p, t).dim() == 0, "форма (batch, 1) тоже даёт скаляр"
