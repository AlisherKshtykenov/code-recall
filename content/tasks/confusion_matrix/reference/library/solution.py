"""confusion_matrix через sklearn."""
from sklearn import metrics  # метрики sklearn


def confusion_matrix(y_true, y_pred, *, labels=None, sample_weight=None, normalize=None):
    """Строка — настоящий класс, столбец — предсказанный. Порядок классов фиксируем через labels."""
    return metrics.confusion_matrix(  # готовая матрица ошибок
        y_true, y_pred,  # настоящие и предсказанные метки
        labels=labels,  # порядок строк и столбцов (на валидации передавайте [0, 1] явно)
        sample_weight=sample_weight,  # веса объектов
        normalize=normalize,  # None — счётчики; "true" / "pred" / "all" — доли
    )


metric = confusion_matrix  # реализация слота metric
