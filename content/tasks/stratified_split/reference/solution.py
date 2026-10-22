"""stratified_split — разбиение на train/test с сохранением долей классов своими руками,
как sklearn.model_selection.train_test_split(..., stratify=y). Сигнатура — та же, что у train_test_split."""
import math
import numbers

import numpy as np


def _check_size(value, name, n):
    """Доля (float в (0, 1)) или число объектов (int в [1, n))."""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} должен быть float в (0, 1) или int, а не {value!r}")
    if isinstance(value, numbers.Integral):
        if value < 1 or value >= n:  # целое — сколько объектов; хотя бы 1 и меньше n
            raise ValueError(f"{name}={value} should be either positive and smaller than the number of samples {n} or a float in the (0, 1) range")
    elif not 0 < value < 1:  # доля — строго между 0 и 1
        raise ValueError(f"The '{name}' parameter must be a float in the range (0.0, 1.0), an int in the range [1, inf) or None")


def _sizes(n, test_size, train_size):
    """(n_train, n_test) по тем же правилам, что в sklearn: test — ceil от доли, train — floor."""
    if test_size is None and train_size is None:
        test_size = 0.25  # по умолчанию четверть — в тест
    _check_size(test_size, "test_size", n)
    _check_size(train_size, "train_size", n)
    if isinstance(test_size, float) and isinstance(train_size, float) and test_size + train_size > 1:
        raise ValueError(f"The sum of test_size and train_size = {test_size + train_size}, should be in the (0, 1) range.")
    n_test = math.ceil(test_size * n) if isinstance(test_size, float) else test_size  # доля -> вверх
    n_train = math.floor(train_size * n) if isinstance(train_size, float) else train_size  # доля -> вниз
    if train_size is None:
        n_train = n - n_test  # остальное — в train
    elif test_size is None:
        n_test = n - n_train  # остальное — в test
    if n_train + n_test > n:
        raise ValueError(f"The sum of train_size and test_size = {n_train + n_test}, should be smaller than the number of samples {n}.")
    if n_train == 0:
        raise ValueError(f"With n_samples={n}, test_size={test_size} and train_size={train_size}, the resulting train set will be empty.")
    return int(n_train), int(n_test)


def _share(counts, n_draws, rng):
    """Сколько взять из каждого класса: пропорционально, округление — по наибольшим остаткам (ничьи — случайно)."""
    exact = counts / counts.sum() * n_draws  # идеальная (дробная) доля класса
    taken = np.floor(exact).astype(int)  # сначала целые части
    left = n_draws - taken.sum()  # сколько ещё раздать
    remainder = exact - taken
    order = np.lexsort((rng.random(len(counts)), -remainder))  # больший остаток — раньше, ничьи — случайно
    taken[order[:left]] += 1
    return taken


def _take(a, idx):
    """Взять строки idx, сохранив тип: numpy, list, pandas (через iloc), torch."""
    if hasattr(a, "iloc"):
        return a.iloc[idx]
    if isinstance(a, list):
        return [a[i] for i in idx]
    return a[idx]


def stratified_split(*arrays, test_size=None, train_size=None, random_state=None, shuffle=True, stratify=None):
    """[a_train, a_test, b_train, b_test, …]: при stratify=y доли классов в train и test — как во всей выборке."""
    if not arrays:
        raise ValueError("At least one array required as input")
    n = len(arrays[0])  # число объектов
    if any(len(a) != n for a in arrays):  # все массивы — про одни и те же объекты
        raise ValueError(f"Found input variables with inconsistent numbers of samples: {[len(a) for a in arrays]}")
    n_train, n_test = _sizes(n, test_size, train_size)
    rng = np.random.default_rng(random_state)  # seed -> повторяемое разбиение

    if not shuffle:
        if stratify is not None:
            raise ValueError("Stratified train/test split is not implemented for shuffle=False")
        train, test = np.arange(n_train), np.arange(n_train, n_train + n_test)  # первые — train, следом — test
    elif stratify is None:
        perm = rng.permutation(n)  # просто перемешать
        train, test = perm[:n_train], perm[n_train:n_train + n_test]
    else:
        y = np.asarray(stratify)
        classes, y_idx = np.unique(y, return_inverse=True)  # номер класса каждого объекта
        counts = np.array([np.sum(y_idx == k) for k in range(len(classes))])  # размер каждого класса
        if counts.min() < 2:  # из класса с одним объектом нельзя положить и в train, и в test
            raise ValueError("The least populated class in y has only 1 member, which is too few. The minimum number of groups for any class cannot be less than 2.")
        if n_train < len(classes):
            raise ValueError(f"The train_size = {n_train} should be greater or equal to the number of classes = {len(classes)}")
        if n_test < len(classes):
            raise ValueError(f"The test_size = {n_test} should be greater or equal to the number of classes = {len(classes)}")
        to_train = _share(counts, n_train, rng)  # сколько объектов каждого класса — в train
        to_test = _share(counts - to_train, n_test, rng)  # из оставшихся — в test
        train, test = [], []
        for k in range(len(classes)):
            members = rng.permutation(np.flatnonzero(y_idx == k))  # объекты класса k в случайном порядке
            train.extend(members[:to_train[k]])
            test.extend(members[to_train[k]:to_train[k] + to_test[k]])
        train, test = rng.permutation(np.array(train)), rng.permutation(np.array(test))  # перемешать классы между собой

    out = []
    for a in arrays:
        out += [_take(a, train), _take(a, test)]  # каждый массив режется одними и теми же индексами
    return out
