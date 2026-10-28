"""holdout_eval через sklearn: train_test_split(stratify) + clone + fit + метрики."""
import numpy as np  # массивы

from sklearn.base import clone  # копия необученной модели
from sklearn.model_selection import train_test_split  # отложенная выборка


def holdout_eval(estimator, X, y, metrics, *, score_metrics=None, test_size=0.2, random_state=None, stratify=True):
    """Отложить test, обучить копию модели на train, посчитать метрики на test."""
    y = np.asarray(y)
    idx = np.arange(len(y))  # номера объектов — чтобы вернуть, что попало в test
    X_tr, X_te, y_tr, y_te, _, idx_te = train_test_split(X, y, idx, test_size=test_size, random_state=random_state,
                                                         stratify=y if stratify else None)  # доли классов сохранены
    model = clone(estimator).fit(X_tr, y_tr)  # переданную модель не трогаем
    pred = model.predict(X_te)  # метки на отложенной выборке
    result = {name: f(y_te, pred) for name, f in metrics.items()}
    if score_metrics:
        if hasattr(model, "predict_proba"):
            scores = model.predict_proba(X_te)[:, 1]  # вероятность положительного класса
        elif hasattr(model, "decision_function"):
            scores = model.decision_function(X_te)  # SVM: «уверенность» без вероятностей
        else:
            raise ValueError("для score_metrics у модели нужен predict_proba или decision_function")
        result.update({name: f(y_te, scores) for name, f in score_metrics.items()})  # pr_auc, roc_auc — по оценкам
    result["n_train"], result["n_test"], result["test_index"] = len(y_tr), len(y_te), np.sort(idx_te)
    return result
