"""f1_score против sklearn.metrics.f1_score: значение, ошибки и предупреждения должны совпадать."""
import numpy as np
import pytest
from sklearn.metrics import f1_score as sk_f1

from likelib import assert_like
from solution import f1_score

BINARY = [
    ([0, 1, 1, 0, 1], [0, 1, 0, 0, 1]),          # обычный случай
    ([1, 1, 1], [1, 1, 1]),                      # всё верно
    ([1, 1, 1], [0, 0, 0]),                      # ничего не нашли
    ([0, 0, 0], [1, 1, 1]),                      # одни ложные тревоги
    ([0, 0, 0], [0, 0, 0]),                      # ни настоящих, ни предсказанных положительных
    ([1], [1]),                                  # один объект
    ([True, False, True], [True, True, False]),  # bool
    ([0.0, 1.0, 1.0], [1.0, 1.0, 0.0]),          # float-метки
]


@pytest.mark.parametrize("y_true, y_pred", BINARY)
def test_binary_like_sklearn(y_true, y_pred):
    assert_like(f1_score, sk_f1, y_true, y_pred)


@pytest.mark.parametrize("pos_label, y_true, y_pred", [
    ("брак", ["брак", "ок", "брак", "ок"], ["брак", "брак", "ок", "ок"]),
    (0, [0, 1, 1, 0], [0, 1, 0, 1]),
    (2, [2, 2], [2, 2]),
])
def test_pos_label(pos_label, y_true, y_pred):
    assert_like(f1_score, sk_f1, y_true, y_pred, pos_label=pos_label)


MULTI = [
    ([0, 1, 2, 2, 1, 0], [0, 2, 2, 1, 1, 0]),
    ([0, 1, 2], [2, 0, 1]),
    (["кот", "пёс", "кот", "лис"], ["кот", "кот", "кот", "лис"]),
    ([3, 3, 3], [3, 3, 3]),
    ([0, 0, 1], [2, 2, 2]),                       # предсказан класс, которого нет в ответах
]


@pytest.mark.parametrize("average", [None, "micro", "macro", "weighted"])
@pytest.mark.parametrize("y_true, y_pred", MULTI)
def test_averages_like_sklearn(y_true, y_pred, average):
    assert_like(f1_score, sk_f1, y_true, y_pred, average=average)


@pytest.mark.parametrize("labels, average", [([1, 2], "micro"), ([2, 0], None), ([0, 5], "macro"), ([5], "weighted"), ([1], "macro")])
def test_labels_subset_order_and_missing(labels, average):
    assert_like(f1_score, sk_f1, [0, 1, 2, 2, 1, 0], [0, 2, 2, 1, 1, 0], labels=labels, average=average)


@pytest.mark.parametrize("average", ["binary", "macro", "weighted", "micro"])
def test_sample_weight(average):
    assert_like(f1_score, sk_f1, [0, 1, 1, 0, 1], [1, 1, 0, 0, 1], sample_weight=[1, 2, 3, 0.5, 4], average=average)


@pytest.mark.parametrize("zero_division", ["warn", 0, 1, np.nan])
@pytest.mark.parametrize("average", ["binary", "macro", "weighted", "micro"])
def test_zero_division(zero_division, average):
    assert_like(f1_score, sk_f1, [0, 0, 0], [0, 0, 0], zero_division=zero_division, average=average, labels=[1] if average != "binary" else None)


@pytest.mark.parametrize("y_true, y_pred, kw", [
    ([], [], {}),
    ([0, 1, 1], [0, 1], {}),
    ([0, 1, 2], [0, 1, 2], {}),
    ([0, 1], [0, 1], {"pos_label": 3}),
    (["a", "b"], ["a", "b"], {}),
    ([0, 1], [0, 1], {"average": "samples"}),
    ([0.5, 1.0], [0.0, 1.0], {}),                # непрерывные значения — не метки классов
])
def test_errors_like_sklearn(y_true, y_pred, kw):
    assert_like(f1_score, sk_f1, y_true, y_pred, **kw)


@pytest.mark.parametrize("seed", range(40))
def test_random_against_sklearn(seed):
    rng = np.random.default_rng(seed)
    for _ in range(15):
        k, n = int(rng.integers(1, 5)), int(rng.integers(1, 30))
        y_true, y_pred = rng.integers(0, k, n), rng.integers(0, k, n)
        average = [None, "binary", "micro", "macro", "weighted"][int(rng.integers(0, 5))]
        assert_like(f1_score, sk_f1, y_true, y_pred, average=average, sample_weight=rng.random(n) if rng.random() < .4 else None)


def test_is_harmonic_mean_of_precision_and_recall():
    from sklearn.metrics import precision_score, recall_score
    y_true, y_pred = [0, 1, 1, 1, 0, 1], [1, 1, 0, 1, 0, 1]
    p, r = precision_score(y_true, y_pred), recall_score(y_true, y_pred)
    assert np.isclose(f1_score(y_true, y_pred), 2 * p * r / (p + r)), "F1 — гармоническое среднее точности и полноты"


def test_does_not_change_inputs():
    y_true, y_pred = np.array([0, 1, 1, 0]), np.array([1, 1, 0, 0])
    f1_score(y_true, y_pred)
    assert y_true.tolist() == [0, 1, 1, 0] and y_pred.tolist() == [1, 1, 0, 0], "входные массивы не должны меняться"
