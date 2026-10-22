"""holdout_eval — оценка на отложенной выборке: стратифицированно отрезать test, обучить копию модели на train,
посчитать метрики на test. Разбиение — мой кирпичик stratified_split."""
import copy

import numpy as np

from bricks.stratified_split import stratified_split


def holdout_eval(estimator, X, y, metrics, *, score_metrics=None, test_size=0.2, random_state=None, stratify=True):
    """metrics: {имя: f(y_true, y_pred)}; score_metrics: {имя: f(y_true, оценки)} — оценки из predict_proba[:, 1]
    или decision_function. Возвращает {имя: значение, "n_train": …, "n_test": …}."""
    y = np.asarray(y)
    X_tr, X_te, y_tr, y_te = stratified_split(X, y, test_size=test_size, random_state=random_state,
                                              stratify=y if stratify else None)  # доли классов — как во всей выборке
    model = copy.deepcopy(estimator)  # переданную модель не трогаем — обучаем копию
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)  # метки на отложенной выборке
    result = {name: f(y_te, pred) for name, f in metrics.items()}
    if score_metrics:
        if hasattr(model, "predict_proba"):
            scores = model.predict_proba(X_te)[:, 1]  # вероятность положительного класса
        elif hasattr(model, "decision_function"):
            scores = model.decision_function(X_te)  # SVM и т.п.: «уверенность» без вероятностей
        else:
            raise ValueError("для score_metrics у модели нужен predict_proba или decision_function")
        result.update({name: f(y_te, scores) for name, f in score_metrics.items()})
    result["n_train"], result["n_test"] = len(y_tr), len(y_te)
    return result
