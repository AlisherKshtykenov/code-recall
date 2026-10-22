"""binary_cross_entropy_with_logits против torch (значения и градиенты), с pos_weight, weight и reduction."""
import pytest
import torch
import torch.nn.functional as F

from likelib import assert_like, close
from solution import binary_cross_entropy_with_logits as bce_logits

torch.manual_seed(0)


def logits(shape, scale=3.0, dtype=torch.float32):
    return (torch.randn(shape) * scale).to(dtype)


def targets(shape, dtype=torch.float32):
    return torch.randint(0, 2, shape).to(dtype)


@pytest.mark.parametrize("shape", [(1,), (8,), (8, 1), (4, 3), (2, 3, 4)])
@pytest.mark.parametrize("reduction", ["mean", "sum", "none"])
def test_values_like_torch(shape, reduction):
    assert_like(bce_logits, F.binary_cross_entropy_with_logits, logits(shape), targets(shape), reduction=reduction)


@pytest.mark.parametrize("pos_weight", [torch.tensor(9.0), torch.tensor([9.0]), torch.tensor(0.5), torch.tensor(1.0)])
def test_pos_weight_scalar(pos_weight):
    assert_like(bce_logits, F.binary_cross_entropy_with_logits, logits((10,)), targets((10,)), pos_weight=pos_weight)


def test_pos_weight_per_class():
    x, t, pw = logits((6, 3)), targets((6, 3)), torch.tensor([1.0, 4.0, 9.0])
    assert_like(bce_logits, F.binary_cross_entropy_with_logits, x, t, pos_weight=pw, reduction="none")


def test_weight_and_pos_weight_together():
    x, t = logits((5, 2)), targets((5, 2))
    assert_like(bce_logits, F.binary_cross_entropy_with_logits, x, t, weight=torch.tensor([0.5, 2.0]), pos_weight=torch.tensor([3.0, 1.0]))


def test_soft_targets():
    assert_like(bce_logits, F.binary_cross_entropy_with_logits, logits((10,)), torch.rand(10), pos_weight=torch.tensor(2.0))


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_large_logits_are_stable(dtype):
    x = torch.tensor([-1000.0, -100.0, -20.0, 0.0, 20.0, 100.0, 1000.0], dtype=dtype)
    t = torch.tensor([1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0], dtype=dtype)
    out = bce_logits(x, t, reduction="none", pos_weight=torch.tensor(3.0, dtype=dtype))
    assert torch.isfinite(out).all(), f"при |x| = 1000 потеря конечна: {out.tolist()}"
    assert close(out, F.binary_cross_entropy_with_logits(x, t, reduction="none", pos_weight=torch.tensor(3.0, dtype=dtype)))


@pytest.mark.parametrize("pos_weight", [None, torch.tensor(9.0), torch.tensor([1.0, 4.0, 9.0])])
@pytest.mark.parametrize("reduction", ["mean", "sum", "none"])
def test_gradient_like_torch(pos_weight, reduction):
    base, t = logits((4, 3), dtype=torch.float64), targets((4, 3), torch.float64)
    pw = pos_weight.double() if pos_weight is not None else None
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    up = torch.rand(4, 3, dtype=torch.float64) if reduction == "none" else torch.tensor(1.0, dtype=torch.float64)
    bce_logits(a, t, reduction=reduction, pos_weight=pw).backward(up)
    F.binary_cross_entropy_with_logits(b, t, reduction=reduction, pos_weight=pw).backward(up)
    assert torch.allclose(a.grad, b.grad), "градиент по логитам как у torch"


def test_gradient_at_zero_and_large_logits():
    base = torch.tensor([-1000.0, -5.0, 0.0, 5.0, 1000.0], dtype=torch.float64)
    t = torch.tensor([1.0, 1.0, 1.0, 0.0, 0.0], dtype=torch.float64)
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    bce_logits(a, t, reduction="sum").backward()
    F.binary_cross_entropy_with_logits(b, t, reduction="sum").backward()
    assert torch.isfinite(a.grad).all() and torch.allclose(a.grad, b.grad), f"градиент σ(x) − t, в нуле −0.5: {a.grad.tolist()}"


def test_equals_bce_of_sigmoid():
    x, t = logits((20,), scale=2.0, dtype=torch.float64), targets((20,), torch.float64)
    assert torch.isclose(bce_logits(x, t), F.binary_cross_entropy(torch.sigmoid(x), t)), "для умеренных логитов = BCE(sigmoid(x))"


def test_pos_weight_scales_only_positives():
    x, t = logits((10,), dtype=torch.float64), targets((10,), torch.float64)
    plain, weighted = bce_logits(x, t, reduction="none"), bce_logits(x, t, reduction="none", pos_weight=torch.tensor(9.0, dtype=torch.float64))
    assert torch.allclose(weighted[t == 1], 9 * plain[t == 1]) and torch.allclose(weighted[t == 0], plain[t == 0]), \
        "pos_weight умножает потерю только положительных примеров"


def test_empty_mean_is_nan():
    assert_like(bce_logits, F.binary_cross_entropy_with_logits, torch.empty(0), torch.empty(0))


@pytest.mark.parametrize("x, t, kw", [
    (torch.tensor([0.5, 0.5]), torch.tensor([[1.0], [0.0]]), {}),       # разные формы
    (torch.tensor([0.5]), torch.tensor([1.0]), {"reduction": "avg"}),   # нет такого reduction
])
def test_errors_like_torch(x, t, kw):
    assert_like(bce_logits, F.binary_cross_entropy_with_logits, x, t, **kw)
