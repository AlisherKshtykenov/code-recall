"""Стена «Детекция дефектов: сравнение»: таблица ablation по recall, кривая обучения, файлы в results/."""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from compare import CNNClassifier, compare

warnings.filterwarnings("ignore")

VARIANTS = {"base", "без весов классов", "sgd вместо adam", "без dropout"}


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    return compare(epochs=6, results_dir=str(tmp_path_factory.mktemp("results")))


def test_table_has_all_variants_sorted_by_recall(res):
    t = res["table"]
    assert isinstance(t, pd.DataFrame) and set(t["variant"]) == VARIANTS, f"в таблице 4 варианта: {t['variant'].tolist()}"
    assert t["recall"].is_monotonic_decreasing, "лучшие по recall — сверху"
    assert {"recall", "f1", "pr_auc", "param.optimizer", "param.use_class_weights", "param.dropout"} <= set(t.columns), "метрики и настройки"


def test_each_variant_changes_one_detail(res):
    cfg = {r["variant"]: r["config"] for r in res["rows"]}
    assert cfg["без весов классов"]["use_class_weights"] is False and cfg["sgd вместо adam"]["optimizer"] == "sgd"
    assert cfg["без dropout"]["dropout"] == 0.0 and cfg["base"]["optimizer"] == "adam", "каждый вариант меняет одну деталь base"


def test_metrics_are_sane(res):
    t = res["table"].set_index("variant")
    assert ((0 <= t[["recall", "f1", "pr_auc"]]) & (t[["recall", "f1", "pr_auc"]] <= 1)).all().all(), "метрики в [0, 1]"
    assert t.loc["base", "recall"] >= 0.5, f"base находит хотя бы половину брака: recall {t.loc['base', 'recall']}"


def test_learning_curve_shapes_and_growth(res):
    sizes, train, test = res["curve"]
    assert list(sizes) == sorted(sizes) and len(sizes) == 3 and train.shape == test.shape == (3, 3), "3 размера × 3 фолда"
    assert test.mean(axis=1)[-1] >= test.mean(axis=1)[0], f"на всех данных recall на тесте не ниже, чем на 30%: {test.mean(axis=1).round(2)}"


def test_files_in_results(res):
    names = {Path(f).name for f in res["files"]}
    assert names == {"benchmark.csv", "benchmark.md", "ablation.png", "learning_curve.png"}, f"файлы: {names}"
    for f in res["files"]:
        assert Path(f).exists() and Path(f).stat().st_size > 0, f"{f} создан и не пустой"
    for f in res["files"]:
        if str(f).endswith(".png"):
            assert Path(f).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{f} — картинка PNG"
    saved = pd.read_csv([f for f in res["files"] if str(f).endswith(".csv")][0])
    assert saved["variant"].tolist() == res["table"]["variant"].tolist(), "csv совпадает с таблицей"


def test_cnn_classifier_is_sklearn_like():
    rng = np.random.default_rng(0)
    X, y = rng.random((40, 1, 16, 16)).astype(np.float32), np.array([0] * 30 + [1] * 10)
    est = CNNClassifier(epochs=1).fit(X, y)
    proba = est.predict_proba(X)
    assert proba.shape == (40, 2) and np.allclose(proba.sum(axis=1), 1), "predict_proba: (N, 2), строки в сумме 1"
    assert set(np.unique(est.predict(X))) <= {0, 1} and 0 <= est.score(X, y) <= 1, "predict — метки, score — recall"
