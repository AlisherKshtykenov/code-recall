"""pr_auc — площадь под PR-кривой как средняя точность (average precision) своими руками,
как sklearn.metrics.average_precision_score: AP = Σ (Rₖ − Rₖ₋₁) · Pₖ по порогам от большего к меньшему."""
import warnings

import numpy as np

AVERAGES = (None, "micro", "macro", "weighted", "samples")


def _binary_ap(y, score, w):
    """AP одного класса: y — 0/1, score — уверенность модели, w — веса объектов."""
    order = np.argsort(-score, kind="mergesort")  # от самой уверенной оценки к наименее (стабильно для равных)
    y, score, w = y[order], score[order], w[order]
    last_of_value = np.r_[np.where(np.diff(score))[0], len(score) - 1]  # порог = каждое разное значение оценки
    tps = np.cumsum(y * w)[last_of_value]  # верно найденные при пороге ≥ score
    fps = np.cumsum((1 - y) * w)[last_of_value]  # ложные тревоги при том же пороге
    predicted = tps + fps  # всего названо положительными
    precision = np.divide(tps, predicted, out=np.zeros_like(tps), where=predicted != 0)  # точность на каждом пороге
    if tps[-1] == 0:  # положительных нет вовсе — полнота не определена, sklearn считает её единицей
        warnings.warn("No positive class found in y_true, recall is set to one for all thresholds which leads to a "
                      "single point in the PR curve.", UserWarning, stacklevel=3)
        recall = np.ones_like(tps)
    else:
        recall = tps / tps[-1]  # полнота на каждом пороге
    steps = np.diff(np.r_[0.0, recall])  # прирост полноты от порога к порогу (первый — от 0)
    return float(np.sum(steps * precision))  # ступенчатая сумма, без интерполяции трапециями


def average_precision_score(y_true, y_score, *, average="macro", pos_label=1, sample_weight=None):
    """Средняя точность по порогам: насколько хорошо модель ставит настоящие объекты класса выше остальных."""
    y_true = np.asarray(y_true)  # к numpy
    y_score = np.asarray(y_score, dtype=float)  # оценки — числа (вероятности, логиты, расстояния)
    if average not in AVERAGES:  # неизвестный способ усреднения
        raise ValueError(f"average должен быть одним из {AVERAGES}, а не {average!r}")
    if len(y_true) == 0:  # на пустом входе не считаем
        raise ValueError("Found empty input array: нужен хотя бы один объект")
    if len(y_true) != len(y_score):  # каждому ответу — одна строка оценок
        raise ValueError(f"Found input variables with inconsistent numbers of samples: [{len(y_true)}, {len(y_score)}]")
    if np.isnan(y_score).any():  # NaN в оценках сломал бы сортировку
        raise ValueError("Input contains NaN.")
    if y_true.dtype.kind == "f" and np.any(y_true != np.round(y_true)):  # ответы — метки, а не непрерывные числа
        raise ValueError("continuous format is not supported")
    w = np.ones(len(y_true)) if sample_weight is None else np.asarray(sample_weight, dtype=float)  # веса объектов
    if y_true.ndim == 2 and y_true.shape[1] == 1:  # столбец (n, 1) — тот же бинарный вектор, как и в sklearn
        y_true, y_score = y_true.ravel(), y_score.reshape(len(y_score), -1)[:, 0] if y_score.ndim == 2 else y_score

    if y_true.ndim == 1 and y_score.ndim == 1:  # бинарная задача: одна оценка на объект
        present = np.unique(y_true)  # метки в ответах
        if len(present) > 2:
            raise ValueError("multiclass format is not supported: для нескольких классов передайте оценки (n, n_classes)")
        if pos_label not in present and len(present) == 2:  # при двух классах положительный обязан быть одним из них
            raise ValueError(f"pos_label={pos_label!r} is not a valid label. It should be one of {list(present)}")
        return _binary_ap((y_true == pos_label).astype(float), y_score, w)

    if y_score.ndim != 2:
        raise ValueError("y_score должен быть одномерным (бинарная задача) или (n, n_classes)")
    if y_true.ndim == 1:  # мультикласс: метки -> one-vs-rest матрица 0/1
        if pos_label != 1:
            raise ValueError("Parameter pos_label is fixed to 1 for multiclass y_true. Do not set pos_label or set pos_label to 1.")
        classes = np.unique(y_true)  # классы по возрастанию — столбцы y_score в том же порядке
        if len(classes) <= 2:  # два класса — это бинарная задача: нужна одна оценка на объект, а не матрица
            raise ValueError("y should be a 1d array: для двух классов передайте оценку положительного класса")
        if len(classes) != y_score.shape[1]:
            raise ValueError("y should be a 1d array: число классов в y_true не совпадает с числом столбцов y_score")
        Y = (y_true[:, None] == classes[None, :]).astype(float)  # Y[i, k] = 1, если объект i из класса k
    else:  # multilabel: y_true уже матрица 0/1
        Y = y_true.astype(float)
        if Y.shape != y_score.shape:
            raise ValueError("y_true и y_score должны быть одной формы")

    if average == "micro":  # все пары (объект, класс) — одна бинарная задача
        return _binary_ap(Y.ravel(), y_score.ravel(), np.repeat(w, Y.shape[1]))
    if average == "samples":  # AP по классам каждого объекта, потом среднее по объектам
        per_row = np.array([_binary_ap(Y[i], y_score[i], np.ones(Y.shape[1])) for i in range(len(Y))])
        return float(np.average(per_row, weights=w))
    support = (Y * w[:, None]).sum(axis=0)  # weighted: вес класса — (взвешенное) число его объектов
    if average == "weighted" and support.sum() == 0:  # положительных нет ни в одном классе — sklearn сразу отдаёт 0
        return 0.0
    per_class = np.array([_binary_ap(Y[:, k], y_score[:, k], w) for k in range(Y.shape[1])])  # AP каждого класса
    if average is None:
        return per_class  # массив по классам
    if average == "macro":
        return float(per_class.mean())  # все классы равны
    return float(np.average(per_class, weights=support))


metric = average_precision_score  # реализация слота metric: metric(y_true, y_score)
