import numpy as np

from solution import train_test_split


def data(n=50):
    X = np.arange(n * 2).reshape(n, 2).astype(float)
    return X, X[:, 0] * 10


def test_sizes():
    X, y = data()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2)
    assert (len(Xtr), len(Xte), len(ytr), len(yte)) == (40, 10, 40, 10)


def test_no_overlap_and_complete():
    X, y = data()
    Xtr, Xte, _, _ = train_test_split(X, y)
    rows = {tuple(r) for r in Xtr} | {tuple(r) for r in Xte}
    assert len(rows) == 50 and not ({tuple(r) for r in Xtr} & {tuple(r) for r in Xte})


def test_aligned():
    X, y = data()
    Xtr, Xte, ytr, yte = train_test_split(X, y)
    assert np.allclose(Xtr[:, 0] * 10, ytr) and np.allclose(Xte[:, 0] * 10, yte)


def test_seed():
    X, y = data()
    a = train_test_split(X, y, seed=1)[1]
    b = train_test_split(X, y, seed=1)[1]
    c = train_test_split(X, y, seed=2)[1]
    assert np.array_equal(a, b) and not np.array_equal(a, c)
