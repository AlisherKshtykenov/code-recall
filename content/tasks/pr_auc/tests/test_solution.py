"""average_precision_score против sklearn: бинарная задача, ничьи в оценках, мультикласс, multilabel, веса, ошибки."""
import numpy as np
import pytest
from sklearn.metrics import average_precision_score as sk_ap
from sklearn.metrics import auc, precision_recall_curve

from likelib import assert_like
from solution import average_precision_score

BINARY = [
    ([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]),          # пример из документации sklearn
    ([0, 1, 1, 0, 1], [0.9, 0.8, 0.7, 0.2, 0.1]),   # первая оценка — ложная тревога
    ([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]),           # идеальное ранжирование
    ([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]),           # худшее ранжирование
    ([0, 1, 1], [0.5, 0.5, 0.5]),                   # все оценки равны (ничья)
    ([0, 1, 0, 1, 1], [0.3, 0.3, 0.7, 0.7, 0.1]),   # ничьи на разных уровнях
    ([1, 1], [0.1, 0.2]),                           # только положительные
    ([0, 0], [0.1, 0.2]),                           # нет положительных: 0 и предупреждение
    ([1], [0.4]),                                   # один объект
    ([0, 1, 1, 0], [-2.0, 3.0, 0.5, -0.1]),         # логиты вместо вероятностей
    ([True, False, True], [0.9, 0.1, 0.2]),         # bool-метки
]


@pytest.mark.parametrize("y_true, y_score", BINARY)
def test_binary_like_sklearn(y_true, y_score):
    assert_like(average_precision_score, sk_ap, y_true, y_score)


@pytest.mark.parametrize("pos_label, y_true", [(0, [0, 1, 0, 1]), ("брак", ["брак", "ок", "ок", "брак"]), ("брак", ["ок", "ок"])])
def test_pos_label(pos_label, y_true):
    assert_like(average_precision_score, sk_ap, y_true, [0.2, 0.9, 0.1, 0.6][:len(y_true)], pos_label=pos_label)


@pytest.mark.parametrize("weights", [[1, 2, 0, 1], [0.5, 0.5, 0.5, 0.5], [3, 0, 0, 1]])
def test_sample_weight(weights):
    assert_like(average_precision_score, sk_ap, [0, 1, 1, 0], [0.5, 0.8, 0.3, 0.6], sample_weight=weights)


SCORES3 = np.array([[.8, .1, .1], [.2, .7, .1], [.1, .2, .7], [.3, .3, .4], [.5, .4, .1], [.2, .2, .6]])


@pytest.mark.parametrize("average", [None, "macro", "weighted", "micro", "samples"])
@pytest.mark.parametrize("y_true", [[0, 1, 2, 1, 0, 2], [0, 1, 2, 2, 2, 2], [2, 1, 0, 0, 1, 1]])
def test_multiclass_one_vs_rest(y_true, average):
    assert_like(average_precision_score, sk_ap, y_true, SCORES3, average=average)


@pytest.mark.parametrize("average", [None, "macro", "weighted", "micro", "samples"])
def test_multilabel(average):
    y = np.array([[1, 0, 1], [0, 1, 1], [1, 1, 0], [0, 0, 1]])
    s = np.array([[.9, .2, .6], [.1, .8, .7], [.6, .4, .2], [.3, .3, .9]])
    assert_like(average_precision_score, sk_ap, y, s, average=average)


def test_multilabel_class_without_positives():
    y, s = np.array([[1, 0], [1, 0]]), np.array([[.9, .2], [.1, .8]])
    assert_like(average_precision_score, sk_ap, y, s, average=None)
    assert_like(average_precision_score, sk_ap, y, s, average="weighted")


@pytest.mark.parametrize("y_true, y_score, kw", [
    ([0, 1], [0.2], {}),                                     # разная длина
    ([0, 1], [0.2, 0.9], {"average": "foo"}),                # нет такого усреднения
    ([0, 1, 1], [np.nan, 0.2, 0.3], {}),                      # NaN в оценках
    ([1.5, 0], [0.1, 0.2], {}),                              # непрерывные ответы
    (["a", "b", "a"], [0.1, 0.5, 0.9], {}),                  # pos_label=1 для строковых меток
    ([0, 1, 2, 1, 0, 2], SCORES3, {"pos_label": 2}),         # в мультиклассе pos_label только 1
])
def test_errors_like_sklearn(y_true, y_score, kw):
    assert_like(average_precision_score, sk_ap, y_true, y_score, **kw)


def test_empty_input_is_error():
    with pytest.raises(ValueError):
        average_precision_score([], [])  # sklearn здесь падает с IndexError — у нас понятная ValueError


@pytest.mark.parametrize("seed", range(40))
def test_random_binary_against_sklearn(seed):
    rng = np.random.default_rng(seed)
    for _ in range(10):
        n = int(rng.integers(1, 40))
        y, s = rng.integers(0, 2, n), np.round(rng.random(n), int(rng.integers(1, 3)))  # округление даёт ничьи
        assert_like(average_precision_score, sk_ap, y, s, sample_weight=rng.random(n) if rng.random() < .4 else None)


def test_not_trapezoid_area():
    y, s = [0, 1, 0, 1, 1, 0, 1], [0.95, 0.9, 0.7, 0.6, 0.4, 0.35, 0.1]
    p, r, _ = precision_recall_curve(y, s)
    ap, trap = average_precision_score(y, s), auc(r, p)
    assert not np.isclose(ap, trap), f"AP — ступенчатая сумма, а не площадь трапециями ({ap:.4f} vs {trap:.4f})"


def test_better_ranking_gives_higher_ap():
    y = [1, 1, 0, 0, 1, 0]
    good, bad = [.9, .8, .3, .2, .7, .1], [.1, .2, .8, .9, .3, .7]
    assert average_precision_score(y, good) > average_precision_score(y, bad), "чем выше настоящие брак в рейтинге, тем больше AP"
