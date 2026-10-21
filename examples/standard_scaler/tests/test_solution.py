import numpy as np

from solution import StandardScaler


def test_train_standardized():
    X = np.random.default_rng(0).normal(5, 3, size=(100, 3))
    Z = StandardScaler().fit_transform(X)
    assert np.allclose(Z.mean(axis=0), 0, atol=1e-9) and np.allclose(Z.std(axis=0), 1)


def test_uses_train_stats():
    tr, te = np.array([[0.0], [2.0]]), np.array([[4.0]])
    s = StandardScaler().fit(tr)
    assert np.allclose(s.transform(te), [[3.0]])


def test_constant_column():
    X = np.array([[1.0, 7.0], [3.0, 7.0]])
    Z = StandardScaler().fit_transform(X)
    assert np.isfinite(Z).all() and np.allclose(Z[:, 1], 0)
