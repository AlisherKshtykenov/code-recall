"""Детекция дефектов: сравнение. Стена baseline + ablation (веса классов, adam/sgd, dropout) + learning_curve
+ benchmark_table. Таблица и графики — в results/."""
from pathlib import Path

import matplotlib
import numpy as np
import torch

from bricks.ablation import ablation
from bricks.adam import Adam
from bricks.baseline import load_images, run, train_model
from bricks.benchmark_table import benchmark_table
from bricks.learning_curve import learning_curve
from bricks.normalize_images import normalize
from bricks.recall import recall_score
from bricks.sgd import SGD

matplotlib.use("Agg")  # без окна: графики — в файлы
import matplotlib.pyplot as plt  # noqa: E402

OPTIMIZERS = {  # у каждого оптимизатора — свой разумный lr
    "adam": lambda params, lr=None: Adam(params, lr=3e-3),
    "sgd": lambda params, lr=None: SGD(params, lr=0.05, momentum=0.9),
}


def build(*, use_class_weights, optimizer, dropout, seed, epochs, data_root="data/images"):
    """Один эксперимент для ablation: обучить и оценить baseline с этими настройками -> метрики."""
    res = run(data_root, seed=seed, epochs=epochs, use_class_weights=use_class_weights, dropout=dropout,
              optimizer_cls=OPTIMIZERS[optimizer])
    return {k: res[k] for k in ("recall", "f1", "pr_auc", "confusion_matrix")}


class CNNClassifier:
    """baseline_cnn как оценщик sklearn (fit / predict / score) — чтобы строить learning_curve."""
    _estimator_type = "classifier"

    def __init__(self, epochs=8, seed=0, threshold=0.5):
        self.epochs, self.seed, self.threshold = epochs, seed, threshold

    def fit(self, X, y):
        self.fit_ = train_model(X, y, epochs=self.epochs, seed=self.seed)  # mean/std — по этому train
        return self

    def predict_proba(self, X):
        m = self.fit_["model"].eval()
        with torch.no_grad():
            p = torch.sigmoid(m(normalize(torch.as_tensor(X, dtype=torch.float32), self.fit_["mean"], self.fit_["std"]))).reshape(-1)
        return np.stack([1 - p.numpy(), p.numpy()], axis=1)

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= self.threshold).astype(int)

    def score(self, X, y):
        return recall_score(np.asarray(y), self.predict(X), zero_division=0)  # качество для кривой — recall


def compare(data_root="data/images", *, epochs=8, repeats=1, seed=0, results_dir="results", curve_sizes=(0.3, 0.6, 1.0), cv=3):
    """-> {table, rows, curve: (sizes, train, test), files}. Файлы: benchmark.csv, benchmark.md, ablation.png, learning_curve.png."""
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = {"use_class_weights": True, "optimizer": "adam", "dropout": 0.3, "seed": seed, "epochs": epochs}
    variants = {"без весов классов": {"use_class_weights": False}, "sgd вместо adam": {"optimizer": "sgd"}, "без dropout": {"dropout": 0.0}}
    rows = ablation(lambda **cfg: build(data_root=data_root, **cfg), variants, base=base, repeats=repeats)  # по одной детали
    table = benchmark_table(rows, sort_by="recall", round_to=3)  # лучшие по recall сверху
    table.to_csv(out / "benchmark.csv", index=False)
    (out / "benchmark.md").write_text(table.to_string(index=False), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(7, 3.5))  # столбики: recall и f1 каждого варианта
    xs = np.arange(len(table))
    ax.bar(xs - 0.2, table["recall"], 0.4, label="recall")
    ax.bar(xs + 0.2, table["f1"], 0.4, label="f1")
    ax.set_xticks(xs, table["variant"], rotation=15)
    ax.set_ylim(0, 1.05)
    ax.set_title("Ablation: что даёт каждая деталь")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "ablation.png", dpi=110)
    plt.close(fig)

    X, y = load_images(data_root)
    sizes, train_s, test_s = learning_curve(CNNClassifier(epochs=epochs, seed=seed), X.numpy(), y.numpy(),
                                            train_sizes=list(curve_sizes), cv=cv)  # стратифицированные фолды
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for scores, name in ((train_s, "train"), (test_s, "test")):
        mean, std = scores.mean(axis=1), scores.std(axis=1)
        ax.plot(sizes, mean, "o-", label=name)
        ax.fill_between(sizes, mean - std, mean + std, alpha=0.2)  # разброс по фолдам
    ax.set_xlabel("объектов в train")
    ax.set_ylabel("recall")
    ax.set_ylim(0, 1.05)
    ax.set_title("Кривая обучения baseline_cnn")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "learning_curve.png", dpi=110)
    plt.close(fig)
    files = [out / n for n in ("benchmark.csv", "benchmark.md", "ablation.png", "learning_curve.png")]
    return {"table": table, "rows": rows, "curve": (sizes, train_s, test_s), "files": files}


if __name__ == "__main__":
    res = compare()
    print(res["table"].to_string(index=False))
    print("кривая обучения (recall на test):", dict(zip(res["curve"][0].tolist(), res["curve"][2].mean(axis=1).round(3).tolist())))
    print("файлы:", ", ".join(str(f) for f in res["files"]))
