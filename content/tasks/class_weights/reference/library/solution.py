"""class_weights через sklearn."""
from sklearn.utils.class_weight import compute_class_weight as sk_compute_class_weight  # готовые веса классов


def compute_class_weight(class_weight, *, classes, y, sample_weight=None):
    """Веса классов: "balanced" — редкий класс весит больше. Считать — только по train."""
    return sk_compute_class_weight(  # n_samples / (n_classes · count_k)
        class_weight,  # "balanced", dict или None
        classes=classes,  # все классы — порядок результата такой же
        y=y,  # метки обучающей выборки
        sample_weight=sample_weight,  # веса объектов (классы считаются по сумме весов)
    )
