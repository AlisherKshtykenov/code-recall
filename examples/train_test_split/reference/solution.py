import numpy as np


def train_test_split(X, y, test_size=0.2, seed=0):
    """Перемешать индексы и отрезать последнюю долю test_size под тест."""
    n = len(X)
    idx = np.random.default_rng(seed).permutation(n)
    n_test = int(round(n * test_size))
    test, train = idx[:n_test], idx[n_test:]
    return X[train], X[test], y[train], y[test]
