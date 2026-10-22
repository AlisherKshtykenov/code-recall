"""batch_norm против torch.nn.functional.batch_norm: выход, градиенты (input, weight, bias) и running stats."""
import pytest
import torch
import torch.nn.functional as F

from likelib import assert_grads_like, assert_like
from solution import batch_norm

torch.manual_seed(0)


def t(*shape, grad=True):
    return torch.randn(*shape, dtype=torch.float64, requires_grad=grad)


def stats(C):
    return torch.randn(C, dtype=torch.float64) * 0.1, torch.rand(C, dtype=torch.float64) + 0.5


@pytest.mark.parametrize("shape", [(8, 3), (4, 3, 5), (4, 3, 6, 6), (2, 3, 2, 3, 4), (2, 1, 5, 5)])
@pytest.mark.parametrize("training", [True, False])
@pytest.mark.parametrize("affine", [True, False])
def test_forward_grads_and_running_stats(shape, training, affine):
    C = shape[1]
    rm, rv = stats(C)
    w, b = (t(C), t(C)) if affine else (None, None)
    assert_grads_like(batch_norm, F.batch_norm, t(*shape), rm, rv, w, b, training=training)


@pytest.mark.parametrize("momentum", [0.0, 0.1, 0.5, 1.0])
def test_momentum(momentum):
    rm, rv = stats(3)
    assert_grads_like(batch_norm, F.batch_norm, t(6, 3, 4, 4), rm, rv, t(3), t(3), training=True, momentum=momentum)


@pytest.mark.parametrize("eps", [1e-5, 1e-3, 0.1])
def test_eps(eps):
    rm, rv = stats(2)
    assert_grads_like(batch_norm, F.batch_norm, t(5, 2, 3), rm, rv, training=True, eps=eps)


def test_training_without_running_stats():
    assert_grads_like(batch_norm, F.batch_norm, t(4, 3, 5, 5), None, None, t(3), t(3), training=True)


def test_running_var_is_unbiased():
    x = torch.randn(4, 2, 3, 3, dtype=torch.float64)
    rm, rv = torch.zeros(2, dtype=torch.float64), torch.ones(2, dtype=torch.float64)
    batch_norm(x, rm, rv, training=True, momentum=1.0)
    per_channel = x.transpose(0, 1).reshape(2, -1)
    assert torch.allclose(rv, per_channel.var(dim=1, unbiased=True)), "в running_var — несмещённая дисперсия (n − 1)"
    assert torch.allclose(rm, per_channel.mean(dim=1)), "в running_mean — среднее батча"


def test_train_output_is_normalized():
    x = torch.randn(16, 3, 8, 8, dtype=torch.float64) * 5 + 2
    out = batch_norm(x, None, None, training=True)
    per_channel = out.transpose(0, 1).reshape(3, -1)
    assert torch.allclose(per_channel.mean(dim=1), torch.zeros(3, dtype=torch.float64), atol=1e-8), "в обучении: среднее канала 0"
    assert torch.allclose(per_channel.var(dim=1, unbiased=False), torch.ones(3, dtype=torch.float64), atol=1e-4), "и дисперсия ≈ 1"


def test_matches_nn_batchnorm_train_then_eval():
    bn = torch.nn.BatchNorm2d(4).double()
    rm, rv = bn.running_mean.clone(), bn.running_var.clone()
    for _ in range(3):
        x = torch.randn(8, 4, 5, 5, dtype=torch.float64)
        assert torch.allclose(batch_norm(x, rm, rv, bn.weight, bn.bias, training=True), bn.train()(x)), "train как у nn.BatchNorm2d"
    x = torch.randn(2, 4, 5, 5, dtype=torch.float64)
    assert torch.allclose(rm, bn.running_mean) and torch.allclose(rv, bn.running_var), "накопленные статистики как у nn.BatchNorm2d"
    assert torch.allclose(batch_norm(x, rm, rv, bn.weight, bn.bias, training=False), bn.eval()(x)), "eval как у nn.BatchNorm2d"


@pytest.mark.parametrize("args, kw", [
    ((torch.randn(4, 3), None, None), {"training": False}),               # eval без статистик
    ((torch.randn(1, 3), None, None), {"training": True}),                # одно значение на канал
    ((torch.randn(4, 3), torch.zeros(2), torch.ones(2)), {}),             # статистики не той длины
    ((torch.randn(3), torch.zeros(3), torch.ones(3)), {}),                # нет оси каналов
])
def test_errors_like_torch(args, kw):
    assert_like(batch_norm, F.batch_norm, *args, **kw)
