"""confusion_matrix против sklearn.metrics.confusion_matrix: значения, dtype, ошибки."""
import numpy as np
import pytest
from sklearn.metrics import confusion_matrix as sk_cm

from likelib import assert_like
from solution import confusion_matrix

CASES = [
    ([0, 1, 1, 0, 1], [0, 1, 0, 0, 1]),           # бинарный
    ([1], [1]),                                   # один объект
    ([0, 0, 0], [0, 0, 0]),                       # один класс
    ([0, 1, 2, 2, 1], [0, 2, 2, 1, 1]),           # три класса
    ([0, 1, 2], [2, 0, 1]),                       # ни одного попадания
    (["брак", "ок", "брак"], ["ок", "ок", "брак"]),  # строковые метки
    ([True, False, True], [True, True, False]),   # bool
    ([0.0, 1.5, 1.5], [1.5, 1.5, 0.0]),           # float-метки
    (np.array([3, 1, 3], dtype=np.int8), np.array([1, 1, 3], dtype=np.int8)),
    ([0, 0, 1], [2, 2, 2]),                       # предсказанный класс, которого нет в ответах
]


@pytest.mark.parametrize("y_true, y_pred", CASES)
def test_counts_like_sklearn(y_true, y_pred):
    assert_like(confusion_matrix, sk_cm, y_true, y_pred)


@pytest.mark.parametrize("normalize", [None, "true", "pred", "all"])
@pytest.mark.parametrize("y_true, y_pred", CASES[:6])
def test_normalize(y_true, y_pred, normalize):
    assert_like(confusion_matrix, sk_cm, y_true, y_pred, normalize=normalize)


@pytest.mark.parametrize("labels", [[1, 0], [0], [2, 1, 0], [1, 5], [0, 1, 2, 3]])
def test_labels_order_subset_extra(labels):
    assert_like(confusion_matrix, sk_cm, [0, 1, 2, 2, 1], [0, 2, 2, 1, 1], labels=labels)


@pytest.mark.parametrize("weights", [[1, 2, 3, 4, 5], [0.5, 1, 1.5, 2, 0], [True, False, True, True, False]])
@pytest.mark.parametrize("normalize", [None, "true"])
def test_sample_weight(weights, normalize):
    assert_like(confusion_matrix, sk_cm, [0, 1, 1, 0, 1], [1, 1, 0, 0, 1], sample_weight=weights, normalize=normalize)


@pytest.mark.parametrize("y_true, y_pred, kw", [
    ([], [], {}),                                  # пустой вход
    ([0, 1], [0], {}),                             # разная длина
    ([0, 1], [0, 1], {"labels": []}),              # пустой labels
    ([0, 1], [0, 1], {"labels": [7]}),             # ни одного класса из labels в ответах
    ([0, 1], [0, 1], {"normalize": "rows"}),       # нет такой нормировки
])
def test_errors_like_sklearn(y_true, y_pred, kw):
    assert_like(confusion_matrix, sk_cm, y_true, y_pred, **kw)


@pytest.mark.parametrize("seed", range(30))
def test_random_against_sklearn(seed):
    rng = np.random.default_rng(seed)
    for _ in range(10):
        k, n = int(rng.integers(1, 6)), int(rng.integers(1, 40))
        y_true, y_pred = rng.integers(0, k, n), rng.integers(0, k, n)
        kw = {"normalize": [None, "true", "pred", "all"][int(rng.integers(0, 4))]}
        if rng.random() < .4:
            kw["sample_weight"] = rng.random(n)
        assert_like(confusion_matrix, sk_cm, y_true, y_pred, **kw)


def test_dtype_like_sklearn():
    assert confusion_matrix([0, 1], [0, 1]).dtype == sk_cm([0, 1], [0, 1]).dtype, "без весов — целые счётчики (int64)"
    assert confusion_matrix([0, 1], [0, 1], sample_weight=[.5, 1]).dtype == np.float64, "с дробными весами — float64"


def test_rows_are_truth_columns_are_prediction():
    cm = confusion_matrix([1, 1, 1], [0, 0, 1])
    assert cm.tolist() == [[0, 0], [2, 1]], "строка — настоящий класс, столбец — предсказанный: 2 объекта класса 1 ушли в 0"
