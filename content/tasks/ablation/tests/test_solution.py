"""ablation: поведение на игрушечной build_fn — base первым, каждый вариант меняет только свои параметры,
base не портится, опечатки ловятся, повторы дают среднее и разброс."""
import numpy as np
import pytest

from solution import ablation

BASE = {"weights": True, "optimizer": "adam", "dropout": 0.5, "seed": 0}
VARIANTS = {"без весов": {"weights": False}, "sgd": {"optimizer": "sgd"}, "без dropout": {"dropout": 0.0}}


def toy(weights, optimizer, dropout, seed):
    """«Обучение»: recall выше с весами и adam, dropout чуть помогает; seed даёт шум."""
    noise = np.random.default_rng(seed).normal(0, 0.01)
    recall = 0.6 + 0.2 * weights + 0.1 * (optimizer == "adam") + 0.05 * (dropout > 0) + noise
    return {"recall": recall, "f1": recall - 0.1, "cm": np.array([[1, 2], [3, 4]])}


def test_rows_order_and_base_first():
    rows = ablation(toy, VARIANTS, base=BASE)
    assert [r["variant"] for r in rows] == ["base", "без весов", "sgd", "без dropout"], "base первым, дальше — варианты по порядку"


def test_each_variant_changes_only_its_params():
    rows = {r["variant"]: r for r in ablation(toy, VARIANTS, base=BASE)}
    for name, changes in VARIANTS.items():
        cfg = rows[name]["config"]
        assert all(cfg[k] == v for k, v in changes.items()), f"{name}: изменения применены"
        assert all(cfg[k] == BASE[k] for k in BASE if k not in changes), f"{name}: остальное — как в base"


def test_effects_are_visible():
    rows = {r["variant"]: r for r in ablation(toy, VARIANTS, base=BASE)}
    assert rows["без весов"]["recall"] < rows["base"]["recall"] - 0.15, "без весов классов recall падает"
    assert rows["sgd"]["recall"] < rows["base"]["recall"], "sgd хуже adam (в игрушке)"


def test_base_not_mutated():
    base = {"weights": True, "optimizer": "adam", "dropout": 0.5, "seed": 0, "layers": [16, 32]}
    before = {k: (list(v) if isinstance(v, list) else v) for k, v in base.items()}

    def build(**cfg):
        cfg["layers"].append(64)  # build_fn может портить свой config — base от этого не страдает
        return {"recall": 1.0}
    ablation(build, {"x": {"dropout": 0.0}}, base=base)
    assert base == before, "base не меняется"


def test_typo_in_variant_is_error():
    with pytest.raises(ValueError):
        ablation(toy, {"опечатка": {"dropuot": 0.0}}, base=BASE)


def test_non_strict_allows_new_params():
    rows = ablation(lambda **cfg: {"n": len(cfg)}, {"новый": {"extra": 1}}, base={"a": 1}, strict=False)
    assert rows[1]["n"] == 2, "strict=False: вариант может добавить параметр"


def test_repeats_mean_and_std():
    rows = ablation(toy, {"без весов": {"weights": False}}, base=BASE, repeats=5)
    r = rows[0]
    assert "recall_std" in r and 0 < r["recall_std"] < 0.05, "при repeats > 1 — среднее и разброс по seed"
    single = [toy(**{**BASE, "seed": s})["recall"] for s in range(5)]
    assert np.isclose(r["recall"], np.mean(single)), "среднее по запускам с seed = 0…4"
    assert isinstance(r["cm"], list) and len(r["cm"]) == 5, "не числа (матрицы) — списком по запускам"


def test_without_base():
    rows = ablation(lambda **cfg: {"recall": cfg.get("p", 0)}, {"p=1": {"p": 1}}, strict=False)
    assert rows[0]["config"] == {} and rows[1]["recall"] == 1, "base по умолчанию пустой"
