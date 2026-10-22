"""binary_cross_entropy против torch.nn.functional.binary_cross_entropy (значения и градиенты),
log_loss против sklearn.metrics.log_loss."""
import numpy as np
import pytest
import torch
import torch.nn.functional as F
from sklearn.metrics import log_loss as sk_log_loss

from likelib import assert_like, close
from solution import binary_cross_entropy, log_loss

torch.manual_seed(0)


def probs(shape, dtype=torch.float32):
    return (torch.rand(shape) * 0.98 + 0.01).to(dtype)


def targets(shape, dtype=torch.float32):
    return torch.randint(0, 2, shape).to(dtype)


@pytest.mark.parametrize("shape", [(1,), (8,), (8, 1), (4, 3), (2, 3, 4)])
@pytest.mark.parametrize("reduction", ["mean", "sum", "none"])
def test_bce_values_like_torch(shape, reduction):
    assert_like(binary_cross_entropy, F.binary_cross_entropy, probs(shape), targets(shape), reduction=reduction)


def test_bce_soft_targets():
    assert_like(binary_cross_entropy, F.binary_cross_entropy, probs((10,)), torch.rand(10))  # target — не только 0/1


def test_bce_edges_clamped_to_100():
    p, t = torch.tensor([0.0, 1.0, 0.0, 1.0]), torch.tensor([1.0, 0.0, 0.0, 1.0])
    assert_like(binary_cross_entropy, F.binary_cross_entropy, p, t, reduction="none")  # −log(0) обрезан до 100


@pytest.mark.parametrize("weight_shape", [(6,), (1,), ()])
def test_bce_weight(weight_shape):
    p, t, w = probs((6,)), targets((6,)), torch.rand(weight_shape) + 0.5
    assert_like(binary_cross_entropy, F.binary_cross_entropy, p, t, weight=w)


def test_bce_per_channel_weight():
    p, t, w = probs((5, 3)), targets((5, 3)), torch.tensor([1.0, 2.0, 0.5])
    assert_like(binary_cross_entropy, F.binary_cross_entropy, p, t, weight=w, reduction="sum")


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_bce_dtype(dtype):
    p, t = probs((7,), dtype), targets((7,), dtype)
    out = binary_cross_entropy(p, t)
    assert out.dtype == dtype and close(out, F.binary_cross_entropy(p, t)), f"dtype {dtype} и значение как у torch"


@pytest.mark.parametrize("reduction", ["mean", "sum", "none"])
@pytest.mark.parametrize("with_weight", [False, True])
def test_bce_gradient_like_torch(reduction, with_weight):
    base, t = probs((4, 3), torch.float64), targets((4, 3), torch.float64)
    w = torch.rand(4, 3, dtype=torch.float64) + 0.5 if with_weight else None
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    up = torch.rand(4, 3, dtype=torch.float64) if reduction == "none" else torch.tensor(1.0, dtype=torch.float64)
    binary_cross_entropy(a, t, weight=w, reduction=reduction).backward(up)
    F.binary_cross_entropy(b, t, weight=w, reduction=reduction).backward(up)
    assert torch.allclose(a.grad, b.grad), "градиент по input как у torch"


def test_bce_gradient_at_edges_like_torch():
    base, t = torch.tensor([0.0, 1.0, 0.5, 1e-9]), torch.tensor([1.0, 0.0, 1.0, 1.0])
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    binary_cross_entropy(a, t, reduction="sum").backward()
    F.binary_cross_entropy(b, t, reduction="sum").backward()
    assert torch.allclose(a.grad, b.grad), f"градиент на краях как у torch (±1e12): {a.grad.tolist()} vs {b.grad.tolist()}"


def test_bce_empty_mean_is_nan():
    assert_like(binary_cross_entropy, F.binary_cross_entropy, torch.empty(0), torch.empty(0))


@pytest.mark.parametrize("p, t, kw", [
    (torch.tensor([1.5]), torch.tensor([1.0]), {}),                     # не вероятность
    (torch.tensor([-0.1]), torch.tensor([0.0]), {}),
    (torch.tensor([0.5, 0.5]), torch.tensor([[1.0], [0.0]]), {}),       # разные формы
    (torch.tensor([0.5]), torch.tensor([1]), {}),                       # long-метки
    (torch.tensor([0.5]), torch.tensor([1.0]), {"reduction": "avg"}),   # нет такого reduction
])
def test_bce_errors_like_torch(p, t, kw):
    assert_like(binary_cross_entropy, F.binary_cross_entropy, p, t, **kw)


@pytest.mark.parametrize("y_true, y_proba, kw", [
    ([0, 1, 1], [0.1, 0.8, 0.7], {}),
    ([0, 1, 1], [0.0, 1.0, 1.0], {}),                                  # идеально: обрезка eps
    ([0, 1, 1], [1.0, 0.0, 0.0], {}),                                  # совсем неверно: −log(eps)
    ([1, 1], [0.9, 0.8], {"labels": [0, 1]}),                          # один класс в y_true — нужен labels
    (["ок", "брак", "ок"], [0.2, 0.7, 0.4], {}),                       # строки: P(класса, второго по алфавиту)
    ([0, 1, 1], [0.1, 0.8, 0.7], {"normalize": False}),
    ([0, 1, 1], [0.1, 0.8, 0.7], {"sample_weight": [1, 2, 3]}),
    ([0, 1, 2], [[0.8, 0.1, 0.1], [0.2, 0.7, 0.1], [0.1, 0.2, 0.7]], {}),  # многоклассовая
    ([0, 1, 2], [[0.8, 0.1, 0.1], [0.2, 0.7, 0.1], [0.1, 0.2, 0.6]], {}),  # строки не в сумме 1 — предупреждение
    ([0, 1], [[0.8, 0.2], [0.3, 0.7]], {}),                            # бинарная двумя столбцами
    ([0, 1, 1], np.array([0.1, 0.8, 1.0], dtype=np.float32), {}),       # float32: другой eps
])
def test_log_loss_like_sklearn(y_true, y_proba, kw):
    assert_like(log_loss, sk_log_loss, y_true, y_proba, **kw)


@pytest.mark.parametrize("y_true, y_proba, kw", [
    ([1, 1], [0.9, 0.8], {}),                                          # один класс без labels
    ([0, 1], [0.2], {}),                                               # разная длина
    ([], [], {}),                                                      # пусто
    ([0, 1, 2], [0.2, 0.5, 0.3], {}),                                  # 3 класса, но одна вероятность
    ([0, 1], [-0.1, 1.2], {}),                                         # не вероятности
    ([0, 1, 2], [[0.8, 0.1, 0.1], [0.2, 0.7, 0.1], [0.1, 0.2, 0.7]], {"labels": [0, 1, 2, 3]}),
])
def test_log_loss_errors_like_sklearn(y_true, y_proba, kw):
    assert_like(log_loss, sk_log_loss, y_true, y_proba, **kw)


@pytest.mark.parametrize("seed", range(30))
def test_log_loss_random_against_sklearn(seed):
    rng = np.random.default_rng(seed)
    k = int(rng.integers(2, 5))
    n = int(rng.integers(k, 40))  # не меньше классов: каждый класс встречается
    y = rng.integers(0, k, n)
    y[:k] = np.arange(k)
    p = rng.dirichlet(np.ones(k), n) if k > 2 or rng.random() < .5 else rng.random(n)
    assert_like(log_loss, sk_log_loss, y, p, sample_weight=rng.random(n) if rng.random() < .4 else None)


def test_bce_equals_log_loss_on_binary():
    p, t = probs((20,), torch.float64), targets((20,), torch.float64)
    assert np.isclose(binary_cross_entropy(p, t).item(), log_loss(t.numpy(), p.numpy())), "это одна и та же потеря"
