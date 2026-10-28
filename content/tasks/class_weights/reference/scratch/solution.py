"""class_weights — веса классов против дисбаланса своими руками, как sklearn.utils.class_weight.compute_class_weight."""
import numpy as np


def compute_class_weight(class_weight, *, classes, y, sample_weight=None):
    """Вес каждого класса из classes: "balanced" — редкий класс весит больше, dict — заданные веса, None — все 1."""
    classes = np.asarray(classes)  # классы, для которых нужны веса (порядок результата — такой же)
    y = np.asarray(y)  # метки обучающей выборки
    if not (class_weight is None or class_weight == "balanced" or isinstance(class_weight, dict)):
        raise ValueError(f"class_weight должен быть 'balanced', dict или None, а не {class_weight!r}")
    if set(y.tolist()) - set(classes.tolist()):  # в y есть метка, которой нет в classes
        raise ValueError("classes should include all valid labels that can be in y")

    if class_weight is None or (isinstance(class_weight, dict) and len(class_weight) == 0):
        return np.ones(len(classes), dtype=np.float64)  # без весов — все классы равны

    if class_weight == "balanced":
        index = {c: i for i, c in enumerate(classes.tolist())}  # метка -> позиция в classes
        if len(set(y.tolist())) != len(classes):  # у каждого класса из classes должны быть объекты в y
            raise ValueError("classes should have valid labels that are in y")
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype=np.float64)  # веса объектов
        counts = np.zeros(len(classes))  # (взвешенное) число объектов каждого класса
        for label, weight in zip(y.tolist(), w.tolist()):
            counts[index[label]] += weight
        return w.sum() / (len(classes) * counts)  # n_samples / (n_classes · count_k): при равных классах — все 1

    # dict: заданные веса, остальные классы — 1
    weight = np.ones(len(classes), dtype=np.float64)
    unweighted = []  # классы из classes, которых нет в словаре
    for i, c in enumerate(classes.tolist()):
        if c in class_weight:
            weight[i] = class_weight[c]
        else:
            unweighted.append(c)
    if unweighted and len(classes) - len(unweighted) != len(class_weight):  # в словаре есть ключ не из classes
        raise ValueError(f"The classes, {unweighted}, are not in class_weight")
    return weight
