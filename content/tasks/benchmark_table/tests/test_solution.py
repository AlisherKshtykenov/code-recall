"""benchmark_table: структура таблицы, сортировка по recall, оба формата входа, матрицы не попадают, ошибки."""
import numpy as np
import pandas as pd
import pytest

from solution import benchmark_table

ROWS = [
    {"variant": "base", "config": {"weights": True, "optimizer": "adam"}, "recall": 0.81, "f1": 0.70, "cm": np.eye(2)},
    {"variant": "без весов", "config": {"weights": False, "optimizer": "adam"}, "recall": 0.55, "f1": 0.62, "cm": np.eye(2)},
    {"variant": "sgd", "config": {"weights": True, "optimizer": "sgd"}, "recall": 0.74, "f1": 0.66, "cm": np.eye(2)},
]


def test_sorted_by_recall_best_first():
    t = benchmark_table(ROWS)
    assert isinstance(t, pd.DataFrame) and t["variant"].tolist() == ["base", "sgd", "без весов"], "по recall, лучшие сверху"
    assert t.index.tolist() == [0, 1, 2], "индекс 0…n после сортировки"


def test_columns_metrics_and_params():
    t = benchmark_table(ROWS)
    assert list(t.columns[:3]) == ["variant", "recall", "f1"], "сначала имя, потом метрики"
    assert {"param.weights", "param.optimizer"} <= set(t.columns), "настройки — столбцами param.*"
    assert "cm" not in t.columns, "матрицы в таблицу не идут"


def test_dict_input():
    t = benchmark_table({"baseline_cnn": {"recall": 0.8, "f1": 0.7}, "resnet": {"recall": 0.9, "f1": 0.8}})
    assert t["variant"].tolist() == ["resnet", "baseline_cnn"], "словарь {модель: метрики} тоже можно"


def test_other_sort_and_ascending():
    assert benchmark_table(ROWS, sort_by="f1", ascending=True)["variant"].tolist() == ["без весов", "sgd", "base"]


def test_ties_keep_input_order():
    rows = [{"variant": n, "recall": 0.5} for n in "abc"]
    assert benchmark_table(rows)["variant"].tolist() == ["a", "b", "c"], "при равном recall — исходный порядок"


def test_numpy_scalars_and_rounding():
    t = benchmark_table([{"variant": "x", "recall": np.float32(0.123456)}], round_to=3)
    assert t.loc[0, "recall"] == 0.123, "numpy-числа принимаются, round_to округляет"


def test_without_params():
    assert not any(c.startswith("param.") for c in benchmark_table(ROWS, params=False).columns)


def test_errors():
    with pytest.raises(ValueError):
        benchmark_table([])
    with pytest.raises(ValueError):
        benchmark_table(ROWS, sort_by="accuracy")
