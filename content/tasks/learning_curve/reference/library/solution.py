"""learning_curve через sklearn."""
import numpy as np  # train_sizes по умолчанию

from sklearn import model_selection  # кросс-валидация и кривые


def learning_curve(estimator, X, y, *, groups=None, train_sizes=np.linspace(0.1, 1.0, 5), cv=None, scoring=None,
                   shuffle=False, random_state=None, error_score=np.nan, return_times=False):
    """Кривая обучения: качество на train и test для нескольких размеров обучающей выборки."""
    return model_selection.learning_curve(  # модель клонируется для каждой точки (нужен get_params)
        estimator, X, y,  # модель и данные
        groups=groups,  # группы для splitter-а
        train_sizes=train_sizes,  # доли или числа объектов
        cv=cv,  # число фолдов (для классификатора — стратифицированные) или splitter
        scoring=scoring,  # None — estimator.score; функция scorer(est, X, y)
        shuffle=shuffle, random_state=random_state,  # перемешать train каждого фолда
        error_score=error_score,  # что ставить, если обучение на точке упало
        return_times=return_times,  # вернуть и время
    )
