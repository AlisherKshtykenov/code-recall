"""compute_class_weight против sklearn.utils.class_weight.compute_class_weight."""
import numpy as np
import pytest
from sklearn.utils.class_weight import compute_class_weight as sk_cw

from likelib import assert_like
from solution import compute_class_weight

Y_CASES = [
    [0, 0, 1, 2, 2, 2],                 # три класса разного размера
    [0] * 90 + [1] * 10,                # 10% брака
    [1, 1, 1],                          # один класс
    [0, 1],                             # по одному объекту
    ["ок", "брак", "ок", "ок"],         # строковые метки
    [-1, 1, 1, 1, -1],                  # метки -1 / 1
    [True, False, False],               # bool
]


@pytest.mark.parametrize("y", Y_CASES)
def test_balanced_like_sklearn(y):
    assert_like(compute_class_weight, sk_cw, "balanced", classes=np.unique(y), y=y)


@pytest.mark.parametrize("y", Y_CASES[:4])
def test_balanced_with_sample_weight(y):
    w = np.linspace(0.5, 2.0, len(y))
    assert_like(compute_class_weight, sk_cw, "balanced", classes=np.unique(y), y=y, sample_weight=w)


@pytest.mark.parametrize("class_weight, classes", [
    ({0: 3.0}, [0, 1]),                 # один задан, другой — 1
    ({0: 1.0, 1: 9.0}, [0, 1]),         # все заданы
    ({}, [0, 1]),                       # пустой словарь — как None
    ({"брак": 5}, ["брак", "ок"]),      # строковые ключи
    ({7: 3.0}, [0, 1]),                 # ключ не из classes — ошибка
    ({0: 2.0, 7: 3.0}, [0, 1]),         # и известный, и неизвестный ключ — ошибка
])
def test_dict_weights(class_weight, classes):
    y = [classes[0], classes[-1], classes[0]]
    assert_like(compute_class_weight, sk_cw, class_weight, classes=np.array(classes), y=y)


def test_none_gives_ones():
    assert_like(compute_class_weight, sk_cw, None, classes=np.array([0, 1, 2]), y=[0, 1, 2, 2])


@pytest.mark.parametrize("class_weight, classes, y", [
    ("balanced", [0, 1, 5], [0, 1]),    # класс 5 из classes нет в y
    ("balanced", [0], [0, 1]),          # метка 1 из y нет в classes
    ({0: 3}, [0], [0, 1]),              # то же для словаря
    ("foo", [0, 1], [0, 1]),            # неизвестный режим
])
def test_errors_like_sklearn(class_weight, classes, y):
    assert_like(compute_class_weight, sk_cw, class_weight, classes=np.array(classes), y=y)


@pytest.mark.parametrize("seed", range(30))
def test_random_balanced_against_sklearn(seed):
    rng = np.random.default_rng(seed)
    k = int(rng.integers(1, 6))
    y = rng.integers(0, k, int(rng.integers(k, 60)))
    y[:k] = np.arange(k)  # каждый класс встречается
    assert_like(compute_class_weight, sk_cw, "balanced", classes=np.arange(k), y=y,
                sample_weight=rng.random(len(y)) + 0.1 if rng.random() < .5 else None)


def test_balanced_weights_equalize_classes():
    y = np.array([0] * 90 + [1] * 10)
    w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
    assert np.isclose(w[0] * 90, w[1] * 10), "суммарный вес каждого класса одинаков: редкий класс весит во столько же раз больше"
    assert np.isclose((w[y]).sum(), len(y)), "сумма весов объектов = числу объектов"


def test_pos_weight_for_bce():
    y = np.array([0] * 90 + [1] * 10)
    w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
    assert np.isclose(w[1] / w[0], 9.0), "pos_weight для BCEWithLogitsLoss = w[1] / w[0] = negatives / positives"
