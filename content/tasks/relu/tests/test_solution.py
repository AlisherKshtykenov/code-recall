"""relu против torch.relu: значения, dtype, особые значения и градиенты."""
import pytest
import torch

from likelib import assert_like
from solution import relu

torch.manual_seed(0)


@pytest.mark.parametrize("shape", [(), (1,), (7,), (3, 4), (2, 3, 5, 5), (0, 4)])
def test_values_like_torch(shape):
    assert_like(relu, torch.relu, torch.randn(shape))


@pytest.mark.parametrize("dtype", [torch.float16, torch.float32, torch.float64, torch.int32, torch.int64])
def test_dtype_kept(dtype):
    x = (torch.randn(20) * 10).to(dtype)
    out = relu(x)
    assert out.dtype == dtype and torch.equal(out, torch.relu(x)), f"dtype {dtype}: значения и тип как у torch.relu"


def test_special_values():
    x = torch.tensor([float("nan"), float("inf"), -float("inf"), 0.0, -0.0, 1e-30, -1e-30])
    assert_like(relu, torch.relu, x)


def test_gradient_like_torch():
    base = torch.tensor([-2.0, -1e-6, 0.0, 1e-6, 3.0])
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    w = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0])
    (relu(a) * w).sum().backward()
    (torch.relu(b) * w).sum().backward()
    assert torch.equal(a.grad, b.grad), f"градиент {a.grad.tolist()} ≠ torch {b.grad.tolist()} (в нуле — 0)"


@pytest.mark.parametrize("seed", range(10))
def test_random_gradients(seed):
    g = torch.Generator().manual_seed(seed)
    base = torch.randn(4, 6, generator=g)
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    upstream = torch.randn(4, 6, generator=g)
    relu(a).backward(upstream)
    torch.relu(b).backward(upstream)
    assert torch.allclose(a.grad, b.grad), "градиент совпадает с torch"


def test_does_not_change_input():
    x = torch.randn(10)
    before = x.clone()
    relu(x)
    assert torch.equal(x, before), "вход не меняется (это не inplace)"


def test_not_a_tensor_is_error():
    assert_like(relu, torch.relu, [1.0, -1.0])
