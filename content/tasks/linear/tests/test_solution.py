"""linear против torch.nn.functional.linear: выход и градиенты по input, weight, bias."""
import pytest
import torch
import torch.nn.functional as F

from likelib import assert_grads_like, assert_like
from solution import linear

torch.manual_seed(0)


def t(*shape, grad=True):
    return torch.randn(*shape, dtype=torch.float64, requires_grad=grad)


@pytest.mark.parametrize("in_shape, out_features", [((5,), 3), ((4, 5), 3), ((2, 4, 5), 7), ((2, 3, 4, 5), 1), ((0, 5), 3), ((4, 1), 1)])
@pytest.mark.parametrize("with_bias", [True, False])
def test_forward_and_grads_like_torch(in_shape, out_features, with_bias):
    in_features = in_shape[-1]
    x, w = t(*in_shape), t(out_features, in_features)
    b = t(out_features) if with_bias else None
    assert_grads_like(linear, F.linear, x, w, b)


def test_one_dim_weight():
    assert_grads_like(linear, F.linear, t(4, 3), t(3))  # weight (in,) -> выход без последней оси
    assert_like(linear, F.linear, t(4, 3, grad=False), t(3, grad=False), t((), grad=False))  # а с bias torch даёт ошибку


def test_bias_only_some_grads():
    x, w, b = t(4, 3, grad=False), t(2, 3), t(2, grad=False)
    assert_grads_like(linear, F.linear, x, w, b)  # градиент только по weight


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_dtype(dtype):
    x, w, b = torch.randn(3, 4, dtype=dtype), torch.randn(2, 4, dtype=dtype), torch.randn(2, dtype=dtype)
    out = linear(x, w, b)
    assert out.dtype == dtype and torch.allclose(out, F.linear(x, w, b), atol=1e-5), f"dtype {dtype} и значения как у torch"


def test_matches_nn_linear_module():
    layer = torch.nn.Linear(5, 3)
    x = torch.randn(4, 5)
    assert torch.allclose(linear(x, layer.weight, layer.bias), layer(x)), "те же веса — тот же выход, что у nn.Linear"


@pytest.mark.parametrize("x, w", [(torch.randn(2, 3), torch.randn(4, 5)), (torch.randn(2, 3), torch.randn(4, 2))])
def test_shape_mismatch_is_error(x, w):
    assert_like(linear, F.linear, x, w)
