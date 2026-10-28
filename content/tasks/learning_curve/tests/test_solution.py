"""learning_curve против sklearn.model_selection.learning_curve: те же размеры и оценки на LogisticRegression
и LinearRegression, при любом cv, train_sizes, shuffle и scoring; поведение на любых объектах с fit/predict/score."""
import warnings

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification, make_regression
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import make_scorer, recall_score
from sklearn.model_selection import KFold, ShuffleSplit, StratifiedKFold
from sklearn.model_selection import learning_curve as sk_lc

from likelib import call, close
from solution import learning_curve

X, y = make_classification(n_samples=120, n_features=6, weights=[0.8, 0.2], random_state=0)
Xr, yr = make_regression(n_samples=90, n_features=4, noise=5.0, random_state=0)


def same(kw, est=None, data=(X, y)):
    est = est or LogisticRegression(max_iter=500)
    mine, lib = learning_curve(est, *data, **kw), sk_lc(est, *data, **kw)
    assert len(mine) == len(lib), "столько же выходов"
    for name, a, b in zip(["train_sizes", "train_scores", "test_scores"], mine, lib):
        assert close(a, b, rtol=1e-7, atol=1e-9), f"{name}: {np.round(a, 4).tolist()} ≠ sklearn {np.round(b, 4).tolist()} ({kw})"


@pytest.mark.parametrize("kw", [
    {},                                                     # cv=None -> StratifiedKFold(5)
    {"cv": 3},
    {"train_sizes": [0.2, 0.5, 1.0]},
    {"train_sizes": [10, 30, 60, 96]},                      # абсолютные размеры
    {"cv": KFold(4, shuffle=True, random_state=0)},         # любой splitter
    {"cv": StratifiedKFold(3, shuffle=True, random_state=1)},
    {"cv": ShuffleSplit(4, test_size=0.25, random_state=2)},
    {"shuffle": True, "random_state": 0},                   # перемешать train каждого фолда
    {"shuffle": True, "random_state": 7, "cv": 4},
    {"scoring": make_scorer(recall_score)},                 # своя метрика
])
def test_like_sklearn_on_logistic_regression(kw):
    same(kw)


def test_failed_fits_become_nan_like_sklearn():
    Xs, ys = X[np.argsort(y)], np.sort(y)  # отсортировано: маленький train — один класс, обучение падает
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        same({"cv": KFold(3), "train_sizes": [0.1, 1.0]}, data=(Xs, ys))
    mine = learning_curve(LogisticRegression(max_iter=500), Xs, ys, cv=KFold(3), train_sizes=[0.1, 1.0])[2]
    assert np.isnan(mine[0]).any(), "упавшие точки — NaN (error_score), как в sklearn"


def test_error_score_raise():
    Xs, ys = X[np.argsort(y)], np.sort(y)
    with pytest.raises(ValueError):
        learning_curve(LogisticRegression(max_iter=500), Xs, ys, cv=KFold(3), train_sizes=[0.1, 1.0], error_score="raise")


def test_cv_as_list_of_splits():
    splits = list(StratifiedKFold(4).split(X, y))
    same({"cv": splits})


@pytest.mark.parametrize("kw", [{}, {"cv": 3}, {"train_sizes": [0.3, 1.0]}])
def test_like_sklearn_on_regressor_kfold(kw):
    same(kw, LinearRegression(), (Xr, yr))  # регрессор -> обычный KFold подряд


def test_pandas_input():
    df = pd.DataFrame(X, columns=[f"f{i}" for i in range(6)])
    same({"cv": 3}, data=(df, pd.Series(y)))


def test_return_times():
    out = learning_curve(LogisticRegression(max_iter=500), X, y, cv=3, train_sizes=[0.5, 1.0], return_times=True)
    assert len(out) == 5 and out[3].shape == out[4].shape == (2, 3) and (out[3] > 0).all(), "время обучения и оценки (n_ticks, n_folds)"


def test_duplicate_sizes_removed_with_warning():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sizes = learning_curve(LogisticRegression(max_iter=500), X, y, cv=3, train_sizes=[0.5, 0.5, 1.0])[0]
    assert len(sizes) == 2 and any(issubclass(x.category, RuntimeWarning) for x in w), "дубликаты размеров убираются с RuntimeWarning"


def test_does_not_fit_given_estimator():
    est = LogisticRegression(max_iter=500)
    learning_curve(est, X, y, cv=3)
    assert not hasattr(est, "coef_"), "переданная модель не обучается — обучаются копии"


def test_more_data_helps_on_average():
    sizes, _, test = learning_curve(LogisticRegression(max_iter=500), X, y, cv=5, train_sizes=[0.1, 1.0])
    assert test[1].mean() >= test[0].mean() - 0.02, "на всех данных качество на тесте не хуже, чем на 10%"


@pytest.mark.parametrize("kw", [{"train_sizes": [0.0, 0.5]}, {"train_sizes": [0.5, 1.5]}, {"train_sizes": [0, 10]},
                                {"train_sizes": [10, 500]}, {"cv": 200}])
def test_errors_like_sklearn(kw):
    est = LogisticRegression(max_iter=500)
    mine, lib = call(learning_curve, est, X, y, **kw)[0], call(sk_lc, est, X, y, **kw)[0]
    assert isinstance(mine, str) and mine == lib, f"sklearn: {lib if isinstance(lib, str) else 'без ошибки'}, у вас: {mine if isinstance(mine, str) else 'без ошибки'} ({kw})"
