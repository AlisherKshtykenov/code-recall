"""sigmoid против torch.sigmoid: значения, dtype, устойчивость при больших |x|, градиенты."""
import pytest
import torch

from likelib import assert_like, close
from solution import sigmoid

torch.manual_seed(0)


@pytest.mark.parametrize("shape", [(), (1,), (7,), (3, 4), (2, 3, 5, 5), (0, 4)])
def test_values_like_torch(shape):
    assert_like(sigmoid, torch.sigmoid, torch.randn(shape) * 4)


@pytest.mark.parametrize("dtype, tol", [(torch.float16, 1e-3), (torch.float32, 1e-6), (torch.float64, 1e-12)])
def test_float_dtypes(dtype, tol):
    x = (torch.randn(50) * 6).to(dtype)
    out = sigmoid(x)
    assert out.dtype == dtype, f"dtype должен сохраниться: {dtype}"
    assert close(out, torch.sigmoid(x), rtol=tol, atol=tol), f"значения как у torch.sigmoid ({dtype})"


@pytest.mark.parametrize("dtype", [torch.int32, torch.int64])
def test_int_input_becomes_float(dtype):
    x = torch.tensor([-3, 0, 2], dtype=dtype)
    out = sigmoid(x)
    assert out.dtype == torch.sigmoid(x).dtype and torch.allclose(out, torch.sigmoid(x)), "целые -> float, как в torch"


@pytest.mark.parametrize("dtype", [torch.float16, torch.float32, torch.float64])
def test_large_values_are_stable(dtype):
    x = torch.tensor([-1000.0, -100.0, -30.0, 30.0, 100.0, 1000.0], dtype=dtype)
    out = sigmoid(x)
    assert torch.isfinite(out).all(), f"при больших |x| не должно быть NaN/inf: {out.tolist()}"
    assert close(out, torch.sigmoid(x), atol=1e-6), "и значения как у torch: 0 слева, 1 справа"


def test_special_values():
    assert_like(sigmoid, torch.sigmoid, torch.tensor([float("nan"), float("inf"), -float("inf"), 0.0, -0.0]))


def test_gradient_like_torch_including_large_x():
    base = torch.tensor([-1000.0, -20.0, -1.0, 0.0, 1.0, 20.0, 1000.0], dtype=torch.float64)
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    sigmoid(a).sum().backward()
    torch.sigmoid(b).sum().backward()
    assert torch.isfinite(a.grad).all(), f"градиент без NaN при больших |x|: {a.grad.tolist()}"
    assert torch.allclose(a.grad, b.grad, atol=1e-12), "градиент σ(x)(1 − σ(x)) как у torch"


@pytest.mark.parametrize("seed", range(10))
def test_random_gradients(seed):
    g = torch.Generator().manual_seed(seed)
    base = torch.randn(4, 6, generator=g) * 5
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    upstream = torch.randn(4, 6, generator=g)
    sigmoid(a).backward(upstream)
    torch.sigmoid(b).backward(upstream)
    assert torch.allclose(a.grad, b.grad, atol=1e-6), "градиент совпадает с torch"


def test_symmetry():
    x = torch.linspace(-8, 8, 33)
    assert torch.allclose(sigmoid(-x), 1 - sigmoid(x), atol=1e-6), "σ(−x) = 1 − σ(x)"


def test_not_a_tensor_is_error():
    assert_like(sigmoid, torch.sigmoid, [1.0, -1.0])
