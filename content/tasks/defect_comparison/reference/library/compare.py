"""Детекция дефектов: сравнение на готовых инструментах. Стена baseline + ablation (цикл по вариантам, pandas)
+ sklearn.model_selection.learning_curve + таблица pandas (sort_values). Таблица и графики — в results/."""
import copy
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd  # таблица экспериментов
import torch
from sklearn.base import BaseEstimator, ClassifierMixin  # свой оценщик в стиле sklearn
from sklearn.metrics import recall_score
from sklearn.model_selection import StratifiedKFold, learning_curve  # кривая обучения

from bricks.baseline import load_images, run, train_model

matplotlib.use("Agg")  # без окна: графики — в файлы
import matplotlib.pyplot as plt  # noqa: E402

OPTIMIZERS = {  # у каждого оптимизатора — свой разумный lr
    "adam": lambda params, lr=None: torch.optim.Adam(params, lr=3e-3),
    "sgd": lambda params, lr=None: torch.optim.SGD(params, lr=0.05, momentum=0.9),
}


def build(*, use_class_weights, optimizer, dropout, seed, epochs, data_root="data/images"):
    """Один эксперимент: обучить и оценить baseline с этими настройками -> метрики."""
    res = run(data_root, seed=seed, epochs=epochs, use_class_weights=use_class_weights, dropout=dropout,
              optimizer_cls=OPTIMIZERS[optimizer])
    return {k: res[k] for k in ("recall", "f1", "pr_auc", "confusion_matrix")}


class CNNClassifier(ClassifierMixin, BaseEstimator):
    """baseline как оценщик sklearn: get_params / set_params даёт BaseEstimator, score — ClassifierMixin."""

    def __init__(self, epochs=8, seed=0, threshold=0.5):
        self.epochs, self.seed, self.threshold = epochs, seed, threshold

    def fit(self, X, y):
        self.fit_ = train_model(X, y, epochs=self.epochs, seed=self.seed)
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        m, mean, std = self.fit_["model"].eval(), self.fit_["mean"], self.fit_["std"]
        X = (torch.as_tensor(X, dtype=torch.float32) - mean[None, :, None, None]) / std[None, :, None, None]  # статистики train
        with torch.inference_mode():
            p = torch.sigmoid(m(X)).reshape(-1).numpy()
        return np.stack([1 - p, p], axis=1)

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= self.threshold).astype(int)

    def score(self, X, y):
        return recall_score(np.asarray(y), self.predict(X), zero_division=0)  # качество для кривой — recall


def compare(data_root="data/images", *, epochs=8, repeats=1, seed=0, results_dir="results", curve_sizes=(0.3, 0.6, 1.0), cv=3):
    """-> {table, rows, curve: (sizes, train, test), files}. Файлы: benchmark.csv, benchmark.md, ablation.png, learning_curve.png."""
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = {"use_class_weights": True, "optimizer": "adam", "dropout": 0.3, "seed": seed, "epochs": epochs}
    variants = {"base": {}, "без весов классов": {"use_class_weights": False}, "sgd вместо adam": {"optimizer": "sgd"}, "без dropout": {"dropout": 0.0}}
    rows = []
    for name, changes in variants.items():  # ablation: по одной детали
        config = {**copy.deepcopy(base), **changes}
        runs = [build(data_root=data_root, **{**config, "seed": seed + r}) for r in range(repeats)]
        metrics = pd.DataFrame([{k: v for k, v in r.items() if np.isscalar(v)} for r in runs])  # числа — в таблицу
        row = {"variant": name, "config": config, **metrics.mean().to_dict(), "confusion_matrix": runs[0]["confusion_matrix"]}
        if repeats > 1:
            row.update({f"{k}_std": v for k, v in metrics.std(ddof=0).to_dict().items()})
        rows.append(row)
    table = pd.json_normalize([{k: v for k, v in r.items() if k != "confusion_matrix"} for r in rows])  # config -> config.<имя>
    table = table.rename(columns=lambda c: "param." + c[7:] if c.startswith("config.") else c)
    table = table.sort_values("recall", ascending=False, kind="mergesort").reset_index(drop=True).round(3)  # лучшие по recall сверху
    table.to_csv(out / "benchmark.csv", index=False)
    (out / "benchmark.md").write_text(table.to_string(index=False), encoding="utf-8")
    ax = table.plot.bar(x="variant", y=["recall", "f1"], rot=15, ylim=(0, 1.05), figsize=(7, 3.5), title="Ablation: что даёт каждая деталь")
    ax.figure.tight_layout()
    ax.figure.savefig(out / "ablation.png", dpi=110)
    plt.close(ax.figure)
    X, y = load_images(data_root)
    sizes, train_s, test_s = learning_curve(CNNClassifier(epochs=epochs, seed=seed), X.numpy(), y.numpy(), train_sizes=list(curve_sizes),
                                            cv=StratifiedKFold(cv, shuffle=True, random_state=seed))  # стратифицированные фолды
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for scores, name in ((train_s, "train"), (test_s, "test")):
        mean, std = scores.mean(axis=1), scores.std(axis=1)
        ax.plot(sizes, mean, "o-", label=name)
        ax.fill_between(sizes, mean - std, mean + std, alpha=0.2)  # разброс по фолдам
    ax.set(xlabel="объектов в train", ylabel="recall", ylim=(0, 1.05), title="Кривая обучения baseline_cnn")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "learning_curve.png", dpi=110)
    plt.close(fig)
    files = [out / n for n in ("benchmark.csv", "benchmark.md", "ablation.png", "learning_curve.png")]
    return {"table": table, "rows": rows, "curve": (sizes, train_s, test_s), "files": files}


if __name__ == "__main__":
    res = compare()
    print(res["table"].to_string(index=False))
