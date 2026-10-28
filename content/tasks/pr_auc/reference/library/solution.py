"""pr_auc (average precision) через sklearn."""
import numpy as np  # для проверки входа

from sklearn import metrics  # метрики sklearn


def average_precision_score(y_true, y_score, *, average="macro", pos_label=1, sample_weight=None):
    """Средняя точность по всем порогам — по ВЕРОЯТНОСТЯМ (или логитам), а не по меткам."""
    if len(np.asarray(y_true)) == 0:  # sklearn на пустом входе падает с IndexError — даём понятную ошибку
        raise ValueError("Found empty input array: нужен хотя бы один объект")
    return metrics.average_precision_score(  # ступенчатая площадь под PR-кривой
        y_true, y_score,  # метки и оценки модели
        average=average,  # для мультикласса / multilabel
        pos_label=pos_label,  # положительный класс
        sample_weight=sample_weight,  # веса объектов
    )


metric = average_precision_score  # реализация слота metric
