"""f1 (F1-мера) своими руками — та же сигнатура и тот же результат, что sklearn.metrics.f1_score.
TP, сумма по строке (настоящие) и по столбцу (предсказанные) — из кирпичика confusion_matrix."""
import warnings

import numpy as np

from bricks.confusion_matrix import confusion_matrix


class UndefinedMetricWarning(UserWarning):
    """Как в sklearn: метрика не определена (деление на ноль), вернули zero_division."""


AVERAGES = (None, "binary", "micro", "macro", "weighted", "samples")


def _zero_value(zero_division):
    return 0.0 if zero_division == "warn" else float(zero_division)  # «warn» — как 0, но с предупреждением


def _warn(zero_division):
    if zero_division == "warn":
        warnings.warn("F-score is ill-defined and being set to 0.0 due to no true nor predicted samples. "
                      "Use `zero_division` parameter to control this behavior.", UndefinedMetricWarning, stacklevel=3)


def f1_score(y_true, y_pred, *, labels=None, pos_label=1, average="binary", sample_weight=None, zero_division="warn"):
    """F1 = 2·TP / (2·TP + FP + FN) — гармоническое среднее precision (точности) и recall (полноты)."""
    y_true = np.asarray(y_true)  # к numpy
    y_pred = np.asarray(y_pred)
    if y_true.ndim != 1 or y_pred.ndim != 1:  # обычные метки классов (не multilabel)
        raise ValueError("y_true и y_pred должны быть одномерными массивами меток")
    if len(y_true) == 0 or len(y_pred) == 0:  # на пустом входе не считаем
        raise ValueError("Found empty input array: нужен хотя бы один объект")
    if len(y_true) != len(y_pred):  # каждому ответу — одно предсказание
        raise ValueError(f"Found input variables with inconsistent numbers of samples: [{len(y_true)}, {len(y_pred)}]")
    for y in (y_true, y_pred):  # метки классов, а не непрерывные числа
        if y.dtype.kind == "f" and np.any(y != np.round(y)):
            raise ValueError("Classification metrics can't handle continuous targets")
    if average not in AVERAGES:  # неизвестный способ усреднения
        raise ValueError(f"average должен быть одним из {AVERAGES}, а не {average!r}")
    if average == "samples":  # усреднение по объектам — только multilabel
        raise ValueError("Samplewise metrics are not available outside of multilabel classification.")
    weights = np.ones(len(y_true)) if sample_weight is None else np.asarray(sample_weight, dtype=float)  # веса объектов
    present = np.unique(np.concatenate([y_true, y_pred]))  # все встреченные метки по возрастанию

    if average == "binary":
        if len(present) > 2:  # F1 одного класса имеет смысл только для двух классов
            raise ValueError("Target is multiclass but average='binary'. Please choose another average setting.")
        if len(present) >= 2 and pos_label not in present:  # положительный класс должен существовать
            raise ValueError(f"pos_label={pos_label!r} is not a valid label. It should be one of {list(present)}")
        classes = np.array([pos_label])  # считаем только положительный класс
    else:
        classes = present if labels is None else np.asarray(labels)  # какие классы и в каком порядке

    with warnings.catch_warnings():  # матрица 1×1 предупреждает «один класс» — для F1 это нормально
        warnings.simplefilter("ignore", UserWarning)
        cm = confusion_matrix(y_true, y_pred, sample_weight=weights)  # строки — правда, столбцы — прогноз
    index = {label: i for i, label in enumerate(present.tolist())}  # метка -> номер строки/столбца
    pick = lambda f: np.array([f(index[c]) if c in index else 0.0 for c in classes.tolist()], dtype=float)  # noqa: E731
    tp = pick(lambda i: cm[i, i])  # верно найденные
    true_sum = pick(lambda i: cm[i].sum())  # настоящих объектов класса: TP + FN
    pred_sum = pick(lambda i: cm[:, i].sum())  # предсказано класса: TP + FP

    if average == "micro":  # общие TP и суммы по всем выбранным классам
        tp, true_sum, pred_sum = np.array([tp.sum()]), np.array([true_sum.sum()]), np.array([pred_sum.sum()])

    denom = true_sum + pred_sum  # 2·TP + FP + FN
    empty = denom == 0  # нет ни настоящих, ни предсказанных — F1 не определена
    f1 = np.where(empty, _zero_value(zero_division), 2 * tp / np.where(empty, 1, denom))  # деление без /0
    if empty.any():
        _warn(zero_division)

    if average in ("binary", "micro"):
        return float(f1[0])  # одно число
    if average is None:
        return f1  # массив по классам в порядке classes
    if average == "macro":  # среднее по классам; nan (zero_division=nan) не учитываем
        ok = ~np.isnan(f1)
        return float(f1[ok].mean()) if ok.any() else float("nan")
    # weighted: среднее, взвешенное числом настоящих объектов класса
    if true_sum.sum() == 0:  # у выбранных классов нет настоящих объектов — веса нулевые
        return _zero_value(zero_division) if empty.any() else 0.0  # F1 не определена -> zero_division; определена (=0) -> 0
    ok = ~np.isnan(f1)
    return float((f1[ok] * true_sum[ok]).sum() / true_sum[ok].sum()) if true_sum[ok].sum() else float("nan")


metric = f1_score  # реализация слота metric: metric(y_true, y_pred)
