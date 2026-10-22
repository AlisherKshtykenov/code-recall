"""recall_score против sklearn.metrics.recall_score: значение, ошибки и предупреждения должны совпадать."""
import warnings

import numpy as np
import pytest
from sklearn.metrics import recall_score as sk_recall

from solution import recall_score


def both(*args, **kw):
    """(моё, sklearn) — значение или название ошибки, и было ли предупреждение."""
    out = []
    for f in (recall_score, sk_recall):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                value = f(*args, **kw)
            except ValueError:
                value = "ValueError"
        out.append((value, bool(w)))
    return out


def assert_same(*args, **kw):
    (mine, warned_mine), (ref, warned_ref) = both(*args, **kw)
    if isinstance(ref, str) or isinstance(mine, str):
        assert mine == ref, f"sklearn: {ref}, у вас: {mine} (вход {args}, параметры {kw})"
    else:
        assert np.allclose(mine, ref, equal_nan=True), f"полнота {mine} ≠ sklearn {ref} (вход {args}, параметры {kw})"
    assert warned_mine == warned_ref, (f"предупреждение: у sklearn {'есть' if warned_ref else 'нет'}, у вас {'есть' if warned_mine else 'нет'} "
                                       f"(вход {args}, параметры {kw})")


BINARY = [
    ([0, 1, 1, 0, 1], [0, 1, 0, 0, 1]),          # обычный случай
    ([1, 1, 1], [1, 1, 1]),                      # всё нашли
    ([1, 1, 1], [0, 0, 0]),                      # ничего не нашли
    ([1], [1]),                                  # один объект
    ([0, 0, 0], [0, 1, 0]),                      # нет настоящих положительных
    ([True, False, True], [True, True, False]),  # bool
    ([0.0, 1.0, 1.0], [1.0, 1.0, 0.0]),          # float-метки
    (np.array([0, 1, 1], dtype=np.int8), np.array([1, 1, 1], dtype=np.int8)),  # другой dtype
]


@pytest.mark.parametrize("y_true, y_pred", BINARY)
def test_binary_like_sklearn(y_true, y_pred):
    assert_same(y_true, y_pred)


@pytest.mark.parametrize("pos_label, y_true, y_pred", [
    ("брак", ["брак", "ок", "брак", "ок"], ["брак", "брак", "ок", "ок"]),  # строковые метки
    (0, [0, 1, 1, 0], [0, 1, 0, 1]),                                     # положительный класс — 0
    (2, [2, 2], [2, 2]),                                                  # в данных один класс
])
def test_pos_label(pos_label, y_true, y_pred):
    assert_same(y_true, y_pred, pos_label=pos_label)


MULTI = [
    ([0, 1, 2, 2, 1, 0], [0, 2, 2, 1, 1, 0]),
    ([0, 1, 2], [2, 0, 1]),                      # ни одного попадания
    (["кот", "пёс", "кот", "лис"], ["кот", "кот", "кот", "лис"]),
    ([3, 3, 3], [3, 3, 3]),                      # один класс
]


@pytest.mark.parametrize("average", [None, "micro", "macro", "weighted"])
@pytest.mark.parametrize("y_true, y_pred", MULTI)
def test_averages_like_sklearn(y_true, y_pred, average):
    assert_same(y_true, y_pred, average=average)


@pytest.mark.parametrize("labels, average", [([1, 2], "micro"), ([2, 0], None), ([0, 5], "macro"), ([5], "weighted"), ([1], "macro")])
def test_labels_subset_order_and_missing(labels, average):
    assert_same([0, 1, 2, 2, 1, 0], [0, 2, 2, 1, 1, 0], labels=labels, average=average)


@pytest.mark.parametrize("average", ["binary", "macro", "weighted", "micro"])
def test_sample_weight(average):
    assert_same([0, 1, 1, 0, 1], [1, 1, 0, 0, 1], sample_weight=[1, 2, 3, 0.5, 4], average=average)


@pytest.mark.parametrize("zero_division", ["warn", 0, 1, np.nan])
@pytest.mark.parametrize("average", ["binary", "macro", "weighted", "micro"])
def test_zero_division(zero_division, average):
    assert_same([0, 0, 0], [0, 1, 0], zero_division=zero_division, average=average)  # у класса 1 нет настоящих объектов


@pytest.mark.parametrize("y_true, y_pred, kw", [
    ([], [], {}),                                    # пустой вход
    ([0, 1, 1], [0, 1], {}),                         # разная длина
    ([0, 1, 2], [0, 1, 2], {}),                      # мультикласс при average='binary'
    ([0, 1], [0, 1], {"pos_label": 3}),              # нет такого положительного класса
    (["a", "b"], ["a", "b"], {}),                    # pos_label=1 для строковых меток
    ([0, 1], [0, 1], {"average": "samples"}),        # samples — только multilabel
])
def test_errors_like_sklearn(y_true, y_pred, kw):
    assert_same(y_true, y_pred, **kw)


@pytest.mark.parametrize("seed", range(40))
def test_random_against_sklearn(seed):
    rng = np.random.default_rng(seed)
    for _ in range(15):
        n_classes, size = int(rng.integers(1, 5)), int(rng.integers(1, 30))
        y_true, y_pred = rng.integers(0, n_classes, size), rng.integers(0, n_classes, size)
        average = [None, "binary", "micro", "macro", "weighted"][int(rng.integers(0, 5))]
        kw = {"average": average, "sample_weight": rng.random(size) if rng.random() < .4 else None}
        assert_same(y_true, y_pred, **kw)


def test_returns_python_float_or_array():
    assert isinstance(recall_score([0, 1, 1], [0, 1, 0]), float), "для одного числа нужен float"
    out = recall_score([0, 1, 2], [0, 1, 1], average=None)
    assert isinstance(out, np.ndarray) and out.shape == (3,), "average=None — массив по классам"


def test_does_not_change_inputs():
    y_true, y_pred = np.array([0, 1, 1, 0]), np.array([1, 1, 0, 0])
    recall_score(y_true, y_pred)
    assert y_true.tolist() == [0, 1, 1, 0] and y_pred.tolist() == [1, 1, 0, 0], "входные массивы не должны меняться"
