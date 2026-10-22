"""flatten против torch.flatten: формы, значения, градиент, крайние случаи и ошибки."""
import pytest
import torch

from likelib import assert_grads_like, assert_like
from solution import flatten

torch.manual_seed(0)


@pytest.mark.parametrize("shape", [(2, 3, 4, 5), (7,), (1, 1), (2, 0, 3), (3, 1, 2)])
@pytest.mark.parametrize("dims", [(0, -1), (1, -1), (0, 1), (1, 2), (-2, -1), (-3, -2), (1, 1)])
def test_like_torch(shape, dims):
    x = torch.randn(shape, dtype=torch.float64, requires_grad=True)
    s, e = dims
    if not (-len(shape) <= s < len(shape) and -len(shape) <= e < len(shape)) or (s % len(shape)) > (e % len(shape)):
        assert_like(flatten, torch.flatten, x.detach(), s, e)  # здесь ожидается ошибка, как у torch
        return
    assert_grads_like(flatten, torch.flatten, x, s, e)


def test_default_flattens_everything():
    x = torch.arange(24).reshape(2, 3, 4)
    assert torch.equal(flatten(x), torch.arange(24)), "по умолчанию — все оси в одну, порядок элементов сохраняется (по строкам)"


def test_typical_cnn_use():
    feats = torch.randn(8, 16, 4, 4)
    assert flatten(feats, 1).shape == (8, 256), "(batch, C, H, W) -> (batch, C·H·W) перед linear"


def test_scalar_becomes_vector():
    assert_like(flatten, torch.flatten, torch.tensor(5.0))


def test_same_dims_returns_input():
    x = torch.randn(2, 3, 4)
    assert flatten(x, 1, 1) is x and torch.flatten(x, 1, 1) is x, "start_dim == end_dim: возвращается тот же тензор"


@pytest.mark.parametrize("dtype", [torch.int64, torch.bool, torch.float16])
def test_any_dtype(dtype):
    x = torch.ones(2, 3, dtype=dtype)
    assert_like(flatten, torch.flatten, x)


@pytest.mark.parametrize("x, s, e", [
    (torch.randn(2, 3), 1, 0),     # start после end
    (torch.randn(2, 3), 0, 2),     # ось вне диапазона
    (torch.randn(2, 3), -3, -1),
    (torch.tensor(1.0), 0, 1),
])
def test_errors_like_torch(x, s, e):
    assert_like(flatten, torch.flatten, x, s, e)
