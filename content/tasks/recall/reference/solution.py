"""recall (полнота) своими руками — та же сигнатура и тот же результат, что sklearn.metrics.recall_score."""
import warnings

import numpy as np


class UndefinedMetricWarning(UserWarning):
    """Как в sklearn: метрика не определена (деление на ноль), вернули zero_division."""


AVERAGES = (None, "binary", "micro", "macro", "weighted", "samples")


def _zero_value(zero_division):
    # «warn» ведёт себя как 0, но с предупреждением; иначе — то значение, что передали (0, 1 или nan)
    return 0.0 if zero_division == "warn" else float(zero_division)


def _warn(zero_division, what):
    if zero_division == "warn":  # предупреждаем только в режиме по умолчанию
        warnings.warn(f"Recall is ill-defined and being set to 0.0 {what}. Use `zero_division` parameter to control this behavior.",
                      UndefinedMetricWarning, stacklevel=3)


def recall_score(y_true, y_pred, *, labels=None, pos_label=1, average="binary", sample_weight=None, zero_division="warn"):
    """recall = TP / (TP + FN): какую долю настоящих объектов класса модель нашла."""
    y_true = np.asarray(y_true)  # списки, кортежи, массивы — к numpy
    y_pred = np.asarray(y_pred)  # то же для предсказаний
    if y_true.ndim != 1 or y_pred.ndim != 1:  # поддерживаем обычные метки классов (не multilabel)
        raise ValueError("y_true и y_pred должны быть одномерными массивами меток")
    if len(y_true) == 0 or len(y_pred) == 0:  # sklearn тоже отказывается считать на пустом входе
        raise ValueError("Found empty input array: нужен хотя бы один объект")
    if len(y_true) != len(y_pred):  # каждому ответу — одно предсказание
        raise ValueError(f"Found input variables with inconsistent numbers of samples: [{len(y_true)}, {len(y_pred)}]")
    if average not in AVERAGES:  # неизвестный способ усреднения
        raise ValueError(f"average должен быть одним из {AVERAGES}, а не {average!r}")
    if average == "samples":  # усреднение по объектам бывает только в multilabel
        raise ValueError("Samplewise metrics are not available outside of multilabel classification.")
    weights = np.ones(len(y_true)) if sample_weight is None else np.asarray(sample_weight, dtype=float)  # вес каждого объекта
    present = np.unique(np.concatenate([y_true, y_pred]))  # все метки, что встречаются, по возрастанию

    if average == "binary":
        if len(present) > 2:  # бинарная полнота имеет смысл только для двух классов
            raise ValueError("Target is multiclass but average='binary'. Please choose another average setting.")
        if len(present) >= 2 and pos_label not in present:  # положительный класс должен существовать
            raise ValueError(f"pos_label={pos_label!r} is not a valid label. It should be one of {list(present)}")
        classes = np.array([pos_label])  # считаем полноту только положительного класса
    else:
        classes = present if labels is None else np.asarray(labels)  # labels — какие классы считать и в каком порядке

    tp = np.array([weights[(y_true == c) & (y_pred == c)].sum() for c in classes])  # нашли: правда c и предсказали c
    support = np.array([weights[y_true == c].sum() for c in classes])  # всего настоящих c (TP + FN)

    if average == "micro":  # общий TP / общий (TP + FN) по всем выбранным классам
        if support.sum() == 0:
            _warn(zero_division, "due to no true samples")
            return _zero_value(zero_division)
        return float(tp.sum() / support.sum())

    empty = support == 0  # у класса нет ни одного настоящего объекта — полнота не определена
    per_class = np.where(empty, _zero_value(zero_division), tp / np.where(empty, 1, support))  # деление без /0
    if empty.any():
        _warn(zero_division, "in labels with no true samples")

    if average == "binary":
        return float(per_class[0])  # одно число — полнота положительного класса
    if average is None:
        return per_class  # массив: полнота каждого класса в порядке classes
    if average == "macro":  # простое среднее по классам; nan (zero_division=nan) не учитываем
        ok = ~np.isnan(per_class)
        return float(per_class[ok].mean()) if ok.any() else float("nan")
    # weighted: среднее, взвешенное числом настоящих объектов класса
    if support.sum() == 0:
        return _zero_value(zero_division)
    ok = ~np.isnan(per_class)  # nan-классы выкидываем вместе с их весом
    return float((per_class[ok] * support[ok]).sum() / support[ok].sum()) if support[ok].sum() else float("nan")


metric = recall_score  # реализация слота metric: metric(y_true, y_pred)
