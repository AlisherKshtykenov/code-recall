"""confusion_matrix (матрица ошибок) своими руками — как sklearn.metrics.confusion_matrix."""
import warnings

import numpy as np

NORMALIZE = (None, "true", "pred", "all")


def confusion_matrix(y_true, y_pred, *, labels=None, sample_weight=None, normalize=None):
    """C[i, j] — сколько объектов класса labels[i] модель отнесла к классу labels[j]."""
    y_true = np.asarray(y_true)  # списки и массивы — к numpy
    y_pred = np.asarray(y_pred)
    if y_true.ndim != 1 or y_pred.ndim != 1:  # обычные метки классов, не multilabel
        raise ValueError("y_true и y_pred должны быть одномерными массивами меток")
    if len(y_true) == 0 or len(y_pred) == 0:  # на пустом входе матрицу не строим (как sklearn)
        raise ValueError("Found empty input array: нужен хотя бы один объект")
    if len(y_true) != len(y_pred):  # каждому ответу — одно предсказание
        raise ValueError(f"Found input variables with inconsistent numbers of samples: [{len(y_true)}, {len(y_pred)}]")
    for y in (y_true, y_pred):  # метки классов, а не непрерывные числа (1.5 — это регрессия)
        if y.dtype.kind == "f" and np.any(y != np.round(y)):
            raise ValueError("Classification metrics can't handle continuous targets")
    if normalize not in NORMALIZE:  # как нормировать: по строкам, столбцам, всей матрице
        raise ValueError(f"normalize должен быть одним из {NORMALIZE}")

    if labels is None:
        labels = np.unique(np.concatenate([y_true, y_pred]))  # все встреченные метки по возрастанию
    else:
        labels = np.asarray(labels)  # порядок строк и столбцов задаёт пользователь
        if labels.size == 0:
            raise ValueError("'labels' should contain at least one label.")
        if not np.isin(y_true, labels).any():  # хотя бы один класс из labels должен быть в ответах
            raise ValueError("At least one label specified must be in y_true")

    if sample_weight is None:
        weights = np.ones(len(y_true), dtype=np.int64)  # без весов — целые счётчики
    else:
        weights = np.asarray(sample_weight)
        if len(weights) != len(y_true):
            raise ValueError("sample_weight и y_true разной длины")
        if weights.dtype.kind not in "iub":  # дробные веса — матрица из float
            weights = weights.astype(np.float64)

    index = {label: i for i, label in enumerate(labels.tolist())}  # метка -> номер строки/столбца
    keep = np.isin(y_true, labels) & np.isin(y_pred, labels)  # объекты с метками не из labels не считаем
    rows = np.array([index[v] for v in y_true[keep].tolist()], dtype=np.int64)  # номер строки (правда)
    cols = np.array([index[v] for v in y_pred[keep].tolist()], dtype=np.int64)  # номер столбца (прогноз)
    cm = np.zeros((len(labels), len(labels)), dtype=weights.dtype if weights.dtype.kind == "f" else np.int64)
    np.add.at(cm, (rows, cols), weights[keep])  # прибавить вес объекта в его клетку (повторы складываются)

    if cm.shape == (1, 1):  # один класс: матрица 1×1, а вы, скорее всего, ждали 2×2 — sklearn предупреждает
        warnings.warn("A single label was found in 'y_true' and 'y_pred'. For the confusion matrix to have the correct shape, "
                      "use the 'labels' parameter to pass all known labels.", UserWarning, stacklevel=2)
    if normalize is None:
        return cm
    cm = cm.astype(np.float64)  # доли — всегда float
    with np.errstate(divide="ignore", invalid="ignore"):  # пустая строка/столбец даёт 0/0 — потом станет 0
        if normalize == "true":
            cm = cm / cm.sum(axis=1, keepdims=True)  # доля от настоящего класса (строка в сумме 1)
        elif normalize == "pred":
            cm = cm / cm.sum(axis=0, keepdims=True)  # доля от предсказанного класса (столбец в сумме 1)
        else:
            cm = cm / cm.sum()  # доля от всех объектов
    return np.nan_to_num(cm)  # 0/0 -> 0, как в sklearn


metric = confusion_matrix  # реализация слота metric: metric(y_true, y_pred)
