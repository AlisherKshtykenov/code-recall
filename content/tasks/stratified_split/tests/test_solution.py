"""stratified_split: разбиение случайное, поэтому проверяем свойства и совпадение со sklearn там, где оно детерминировано."""
import numpy as np
import pandas as pd
import pytest
import torch
from sklearn.model_selection import train_test_split as sk_split

from likelib import call
from solution import stratified_split


def data(n=40, share=0.1, k=2):
    y = np.zeros(n, dtype=int)
    y[: max(2, int(n * share))] = 1  # ~10% брака
    if k == 3:
        y[-max(2, n // 4):] = 2
    X = np.arange(n * 2).reshape(n, 2)
    return X, y


@pytest.mark.parametrize("n, kw", [
    (40, {}), (40, {"test_size": 0.3}), (40, {"test_size": 7}), (40, {"train_size": 0.5}), (40, {"train_size": 30}),
    (40, {"train_size": 25, "test_size": 10}), (40, {"train_size": 0.6, "test_size": 0.3}), (21, {"test_size": 0.33}),
    (100, {"test_size": 0.2}), (10, {"test_size": 0.5}),
])
def test_sizes_like_sklearn(n, kw):
    X, y = data(n)
    mine = stratified_split(X, y, stratify=y, random_state=0, **kw)
    lib = sk_split(X, y, stratify=y, random_state=0, **kw)
    assert [len(a) for a in mine] == [len(a) for a in lib], f"размеры частей {[len(a) for a in mine]} ≠ sklearn {[len(a) for a in lib]} ({kw})"


@pytest.mark.parametrize("n, test_size, k", [(40, 0.25, 2), (100, 0.2, 2), (60, 0.3, 3), (33, 0.33, 3), (20, 0.5, 2)])
def test_class_proportions_kept(n, test_size, k):
    X, y = data(n, k=k)
    _, _, y_tr, y_te = stratified_split(X, y, test_size=test_size, stratify=y, random_state=1)
    _, _, s_tr, s_te = sk_split(X, y, test_size=test_size, stratify=y, random_state=1)
    for c in np.unique(y):
        assert abs((y_te == c).sum() - (s_te == c).sum()) <= 1, f"класс {c}: в тесте {(y_te == c).sum()}, у sklearn {(s_te == c).sum()} (допуск ±1)"
        assert abs((y_tr == c).sum() - (s_tr == c).sum()) <= 1, f"класс {c}: в train {(y_tr == c).sum()}, у sklearn {(s_tr == c).sum()}"
        assert (y_tr == c).sum() >= 1 and (y_te == c).sum() >= 1, f"класс {c} должен попасть и в train, и в test"


@pytest.mark.parametrize("stratify", [True, False])
def test_disjoint_complete_and_aligned(stratify):
    X, y = data(50)
    X_tr, X_te, y_tr, y_te = stratified_split(X, y, test_size=0.3, stratify=y if stratify else None, random_state=3)
    rows_tr, rows_te = {tuple(r) for r in X_tr}, {tuple(r) for r in X_te}
    assert not rows_tr & rows_te, "объект не может быть и в train, и в test"
    assert len(rows_tr | rows_te) == 50, "train + test = вся выборка"
    full = {tuple(r): c for r, c in zip(X, y)}
    assert all(full[tuple(r)] == c for r, c in zip(X_tr, y_tr)), "X и y в train перемешаны одинаково"
    assert all(full[tuple(r)] == c for r, c in zip(X_te, y_te)), "X и y в test перемешаны одинаково"


def test_seed_repeatable_and_different_seeds_differ():
    X, y = data(60)
    a = stratified_split(X, y, stratify=y, random_state=7)[1]
    b = stratified_split(X, y, stratify=y, random_state=7)[1]
    c = stratified_split(X, y, stratify=y, random_state=8)[1]
    assert np.array_equal(a, b), "один random_state — одно и то же разбиение"
    assert not np.array_equal(a, c), "разные random_state — разные разбиения"


def test_shuffles_order():
    X, y = data(60)
    X_tr = stratified_split(X, y, stratify=y, random_state=0)[0]
    assert not np.array_equal(X_tr[:, 0], np.sort(X_tr[:, 0])), "строки train должны быть перемешаны, а не идти по порядку"


def test_shuffle_false_like_sklearn():
    X, y = data(20)
    mine, lib = stratified_split(X, y, shuffle=False, test_size=0.25), sk_split(X, y, shuffle=False, test_size=0.25)
    assert all(np.array_equal(m, l) for m, l in zip(mine, lib)), "без перемешивания: первые объекты — train, следующие — test, как в sklearn"


def test_types_are_kept():
    X, y = data(20)
    df, s = pd.DataFrame(X, columns=["a", "b"]), pd.Series(y, name="y")
    d_tr, d_te, s_tr, _ = stratified_split(df, s, stratify=y, random_state=0)
    assert isinstance(d_tr, pd.DataFrame) and isinstance(s_tr, pd.Series), "pandas остаётся pandas"
    assert (d_tr.index == s_tr.index).all(), "индексы DataFrame и Series совпадают"
    l_tr, _ = stratified_split(list(range(20)), stratify=y, random_state=0)
    assert isinstance(l_tr, list), "список остаётся списком"
    t_tr, _ = stratified_split(torch.arange(20), stratify=y, random_state=0)
    assert isinstance(t_tr, torch.Tensor), "torch.Tensor остаётся тензором"


def test_string_labels():
    y = np.array(["ок"] * 16 + ["брак"] * 4)
    _, y_te = stratified_split(y, stratify=y, test_size=0.25, random_state=0)
    assert (y_te == "брак").sum() == 1, "строковые метки стратифицируются так же"


@pytest.mark.parametrize("args, kw", [
    ((), {}),                                                  # нет массивов
    ((np.arange(20), np.arange(5)), {}),                       # разная длина
    ((np.arange(5),), {"stratify": np.array([0, 0, 0, 0, 1])}),  # класс из одного объекта
    ((np.arange(20),), {"test_size": 1.0}),                    # доля 1
    ((np.arange(20),), {"test_size": 0.0}),                    # доля 0
    ((np.arange(20),), {"test_size": 20}),                     # тест = вся выборка
    ((np.arange(20),), {"test_size": -1}),
    ((np.arange(20),), {"test_size": "a"}),
    ((np.arange(20),), {"test_size": 0.6, "train_size": 0.6}),  # сумма > 1
    ((np.arange(20),), {"test_size": 0.99}),                   # train пустой
    ((np.arange(20),), {"shuffle": False, "stratify": np.array([0, 1] * 10)}),  # стратификация без перемешивания
    ((np.arange(20),), {"test_size": 0.01, "stratify": np.array([0] * 14 + [1] * 6)}),  # тест меньше числа классов
])
def test_errors_like_sklearn(args, kw):
    mine, lib = call(stratified_split, *args, **kw)[0], call(sk_split, *args, **kw)[0]
    assert isinstance(mine, str) and mine == lib, f"sklearn: {lib if isinstance(lib, str) else 'без ошибки'}, у вас: {mine if isinstance(mine, str) else 'без ошибки'} ({kw})"


@pytest.mark.parametrize("seed", range(30))
def test_random_sizes_and_strata(seed):
    rng = np.random.default_rng(seed)
    n, k = int(rng.integers(10, 80)), int(rng.integers(2, 4))
    y = rng.integers(0, k, n)
    y[: 2 * k] = np.repeat(np.arange(k), 2)  # в каждом классе хотя бы 2
    test_size = float(np.round(rng.uniform(0.15, 0.5), 2))
    mine, _ = call(stratified_split, np.arange(n), y, stratify=y, test_size=test_size, random_state=seed)
    lib, _ = call(sk_split, np.arange(n), y, stratify=y, test_size=test_size, random_state=seed)
    if isinstance(lib, str):  # sklearn отказался (например, тест меньше числа классов) — и мы должны
        assert mine == lib, f"sklearn: {lib}, у вас: {mine if isinstance(mine, str) else 'без ошибки'}"
        return
    assert [len(a) for a in mine] == [len(a) for a in lib], "размеры как у sklearn"
    for c in range(k):
        assert abs((mine[3] == c).sum() - (lib[3] == c).sum()) <= 1, f"класс {c}: доля в тесте как у sklearn (±1)"
