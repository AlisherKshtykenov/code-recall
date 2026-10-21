import numpy as np


class StandardScaler:
    """(x - mean) / std по колонкам; статистики — только по train."""

    def fit(self, X):
        self.mean_ = X.mean(axis=0)
        std = X.std(axis=0)
        self.std_ = np.where(std == 0, 1.0, std)  # константная колонка — без деления на ноль
        return self

    def transform(self, X):
        return (X - self.mean_) / self.std_

    def fit_transform(self, X):
        return self.fit(X).transform(X)
