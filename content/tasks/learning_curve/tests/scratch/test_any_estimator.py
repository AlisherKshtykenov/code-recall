"""Только «С нуля»: копия модели через deepcopy, поэтому подходит любой объект с fit / predict / score
(sklearn.learning_curve клонирует через get_params и такой объект не примет)."""
import numpy as np
from sklearn.datasets import make_classification

from solution import learning_curve

X, y = make_classification(n_samples=120, n_features=6, weights=[0.8, 0.2], random_state=0)


def test_any_object_with_fit_predict_score():
    class Majority:
        def fit(self, X, y):
            self.value = np.bincount(y).argmax()
            return self

        def predict(self, X):
            return np.full(len(X), self.value)

        def score(self, X, y):
            return float((self.predict(X) == y).mean())
    sizes, train, test = learning_curve(Majority(), X, y, cv=4, train_sizes=[0.25, 1.0])
    assert train.shape == test.shape == (2, 4) and np.allclose(test, test[:1]), "любой объект с fit/predict/score; у «всегда частый класс» качество не растёт"
