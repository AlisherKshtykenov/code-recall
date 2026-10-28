"""recall через sklearn — так полноту считают на практике."""
from sklearn import metrics  # метрики классификации sklearn


def recall_score(y_true, y_pred, *, labels=None, pos_label=1, average="binary", sample_weight=None, zero_division="warn"):
    """Полнота: какую долю настоящего брака нашла модель. Параметры передаём в sklearn как есть."""
    return metrics.recall_score(  # готовая функция: TP / (TP + FN)
        y_true, y_pred,  # настоящие и предсказанные метки (не вероятности)
        labels=labels,  # какие классы считать и в каком порядке
        pos_label=pos_label,  # какой класс — «брак» при average="binary"
        average=average,  # binary / micro / macro / weighted / None
        sample_weight=sample_weight,  # веса объектов
        zero_division=zero_division,  # что вернуть, если настоящих объектов класса нет
    )


metric = recall_score  # реализация слота metric
