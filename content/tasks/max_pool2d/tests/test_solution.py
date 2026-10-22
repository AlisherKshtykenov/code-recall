"""max_pool2d против torch.nn.functional.max_pool2d: выход, индексы, градиенты, ничьи, NaN, ceil_mode, ошибки."""
import pytest
import torch
import torch.nn.functional as F

from likelib import assert_grads_like, assert_like
from solution import max_pool2d

torch.manual_seed(0)


def t(*shape):
    return torch.randn(*shape, dtype=torch.float64, requires_grad=True)


KSP = [(k, s, p) for k, s in [(2, None), (3, None), (2, 1), (3, 2), ((2, 3), (1, 2)), (1, None)] for p in (0, 1)
       if p <= min(k if isinstance(k, tuple) else (k, k)) // 2]  # отступ больше половины окна — в test_errors_like_torch


@pytest.mark.parametrize("kernel, stride, padding", KSP)
def test_kernel_stride_padding(kernel, stride, padding):
    assert_grads_like(max_pool2d, F.max_pool2d, t(2, 3, 9, 8), kernel, stride, padding)


@pytest.mark.parametrize("dilation", [1, 2, (2, 1)])
@pytest.mark.parametrize("ceil_mode", [False, True])
def test_dilation_and_ceil_mode(dilation, ceil_mode):
    assert_grads_like(max_pool2d, F.max_pool2d, t(2, 2, 11, 10), 3, 2, 1, dilation, ceil_mode)


@pytest.mark.parametrize("size", [5, 6, 7])
@pytest.mark.parametrize("ceil_mode", [False, True])
def test_ceil_mode_sizes(size, ceil_mode):
    assert_grads_like(max_pool2d, F.max_pool2d, t(1, 1, size, size), 2, ceil_mode=ceil_mode)


@pytest.mark.parametrize("kw", [{}, {"padding": 1}, {"stride": 1}, {"dilation": 2}, {"ceil_mode": True}])
def test_return_indices_like_torch(kw):
    x = t(2, 3, 7, 7)
    assert_grads_like(max_pool2d, F.max_pool2d, x, 3, return_indices=True, **kw)


def test_ties_pick_first_and_gradient_goes_there():
    x = torch.tensor([[[[1.0, 3.0, 3.0], [2.0, 0.0, 3.0], [1.0, 1.0, 1.0]]]], requires_grad=True)
    assert_grads_like(max_pool2d, F.max_pool2d, x, 2, 1, return_indices=True)  # ничьи: индекс и градиент — у первого


def test_many_ties_random_integers():
    x = torch.randint(0, 3, (2, 2, 8, 8)).double().requires_grad_()
    assert_grads_like(max_pool2d, F.max_pool2d, x, 3, 1, 1, return_indices=True)


def test_nan_wins():
    x = torch.tensor([[[[1.0, float("nan")], [2.0, 3.0]]]])
    assert_like(max_pool2d, F.max_pool2d, x, 2, return_indices=True)


def test_unbatched():
    assert_grads_like(max_pool2d, F.max_pool2d, t(3, 6, 6), 2, return_indices=True)


def test_halves_defect_feature_map():
    x = torch.randn(8, 16, 64, 64)
    assert max_pool2d(x, 2).shape == (8, 16, 32, 32), "окно 2 и шаг 2 уменьшают карту признаков вдвое"


@pytest.mark.parametrize("x, args, kw", [
    (torch.randn(1, 1, 4, 4), (2,), {"padding": 2}),          # отступ больше половины окна
    (torch.randn(1, 1, 1, 1), (3,), {}),                       # окно больше картинки
    (torch.randn(4, 4), (2,), {}),                             # нет оси каналов
])
def test_errors_like_torch(x, args, kw):
    assert_like(max_pool2d, F.max_pool2d, x, *args, **kw)
