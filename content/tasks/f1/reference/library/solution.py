"""f1 через sklearn."""
from sklearn import metrics  # метрики sklearn


def f1_score(y_true, y_pred, *, labels=None, pos_label=1, average="binary", sample_weight=None, zero_division="warn"):
    """F1 — гармоническое среднее точности и полноты. Параметры — как есть в sklearn."""
    return metrics.f1_score(  # готовая F1-мера
        y_true, y_pred,  # метки
        labels=labels,  # какие классы
        pos_label=pos_label,  # положительный класс для binary
        average=average,  # как усреднять по классам
        sample_weight=sample_weight,  # веса объектов
        zero_division=zero_division,  # значение при 0 / 0
    )


metric = f1_score  # реализация слота metric
