"""Контракт слота metric — верен для любой реализации (recall, f1, confusion_matrix, pr_auc…)."""
import numpy as np

from slots.metric import metric

Y_TRUE = [0, 1, 1, 0, 1, 0, 0, 1]
Y_PRED = [0, 1, 0, 0, 1, 1, 0, 1]


def test_returns_number_or_array():
    out = metric(Y_TRUE, Y_PRED)
    assert np.isscalar(out) or isinstance(out, np.ndarray), f"метрика должна вернуть число или массив, а вернула {type(out).__name__}"


def test_list_and_array_same():
    assert np.allclose(metric(Y_TRUE, Y_PRED), metric(np.array(Y_TRUE), np.array(Y_PRED))), "для списка и numpy-массива результат должен совпадать"


def test_does_not_change_inputs():
    yt, yp = np.array(Y_TRUE), np.array(Y_PRED)
    metric(yt, yp)
    assert yt.tolist() == Y_TRUE and yp.tolist() == Y_PRED, "метрика не должна менять входные массивы"


def test_deterministic():
    assert np.allclose(metric(Y_TRUE, Y_PRED), metric(Y_TRUE, Y_PRED)), "одни и те же входы — один и тот же результат"
