"""holdout_eval: на том разбиении, что сделала функция (test_index), — те же метрики, что посчитать руками со sklearn."""
import numpy as np
import pytest
from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, recall_score
from sklearn.svm import LinearSVC

from solution import holdout_eval

X, y = make_classification(n_samples=200, n_features=6, weights=[0.9, 0.1], random_state=0)
METRICS = {"recall": recall_score, "f1": f1_score, "confusion_matrix": confusion_matrix}


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("test_size", [0.2, 0.3])
def test_metrics_like_manual_split(seed, test_size):
    got = holdout_eval(LogisticRegression(max_iter=500), X, y, METRICS, score_metrics={"pr_auc": average_precision_score},
                       test_size=test_size, random_state=seed)
    te = got["test_index"]  # разбиение, которое сделала сама функция (своё или sklearn)
    tr = np.setdiff1d(np.arange(len(y)), te)
    X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]
    assert abs(len(te) - test_size * len(y)) <= 1 and abs(y[te].mean() - y.mean()) < 0.05, "test — нужной доли, брак в нём — как во всей выборке"
    model = LogisticRegression(max_iter=500).fit(X_tr, y_tr)
    pred, prob = model.predict(X_te), model.predict_proba(X_te)[:, 1]
    assert np.isclose(got["recall"], recall_score(y_te, pred)) and np.isclose(got["f1"], f1_score(y_te, pred)), "recall и f1 как руками"
    assert np.array_equal(got["confusion_matrix"], confusion_matrix(y_te, pred)), "матрица ошибок как руками"
    assert np.isclose(got["pr_auc"], average_precision_score(y_te, prob)), "pr_auc по predict_proba[:, 1]"
    assert (got["n_train"], got["n_test"]) == (len(y_tr), len(y_te)), "размеры частей"


def test_repeatable_with_seed():
    a = holdout_eval(LogisticRegression(max_iter=500), X, y, METRICS, random_state=5)
    b = holdout_eval(LogisticRegression(max_iter=500), X, y, METRICS, random_state=5)
    assert np.array_equal(a["confusion_matrix"], b["confusion_matrix"]), "один seed — один и тот же результат"


def test_stratified_test_part_keeps_defect_share():
    got = holdout_eval(LogisticRegression(max_iter=500), X, y, METRICS, test_size=0.2, random_state=0)
    defects_in_test = got["confusion_matrix"][1].sum()
    assert defects_in_test == round(0.2 * y.sum()) or abs(defects_in_test - 0.2 * y.sum()) <= 1, "в тесте ~20% всего брака"


def test_given_model_not_fitted():
    est = LogisticRegression(max_iter=500)
    holdout_eval(est, X, y, METRICS, random_state=0)
    assert not hasattr(est, "coef_"), "переданная модель не обучается — обучается копия"


def test_decision_function_fallback():
    got = holdout_eval(LinearSVC(), X, y, {}, score_metrics={"pr_auc": average_precision_score}, random_state=0)
    assert 0 <= got["pr_auc"] <= 1, "без predict_proba — оценки из decision_function"


def test_no_scores_is_error():
    class NoScores:
        def get_params(self, deep=True):  # чтобы sklearn.clone мог копировать (режим «Библиотека»)
            return {}

        def fit(self, X, y):
            return self

        def predict(self, X):
            return np.zeros(len(X), dtype=int)
    with pytest.raises(ValueError):
        holdout_eval(NoScores(), X, y, {}, score_metrics={"pr_auc": average_precision_score}, random_state=0)


def test_without_stratify_still_works():
    got = holdout_eval(LogisticRegression(max_iter=500), X, y, METRICS, random_state=0, stratify=False)
    assert got["n_test"] == 40, "без стратификации — та же доля в тест"
