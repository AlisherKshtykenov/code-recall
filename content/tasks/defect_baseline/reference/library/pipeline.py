"""Детекция дефектов: baseline CNN — вся цепочка на готовых инструментах.
картинки -> train_test_split(stratify) -> mean/std по train -> compute_class_weight -> nn.Sequential (Conv2d…)
-> BCEWithLogitsLoss(pos_weight) + Adam -> sklearn.metrics (recall, f1, average_precision, confusion_matrix)."""
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, recall_score  # метрики
from sklearn.model_selection import train_test_split  # стратифицированное разбиение
from sklearn.utils.class_weight import compute_class_weight  # веса редкого класса
from torch import nn  # готовые слои
from torch.utils.data import DataLoader, TensorDataset

POSITIVE = ("defect", "брак", "bad", "ng")  # как может называться папка с браком


def load_images(root="data/images", size=64):
    """<root>/ok/*.png и <root>/defect/*.png -> X (N, 1, size, size) в [0, 1], y (N,)."""
    root = Path(root)
    images, labels = [], []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        label = int(folder.name.lower() in POSITIVE)  # 1 — брак, 0 — норма
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
                images.append(np.asarray(Image.open(f).convert("L").resize((size, size)), dtype=np.float32) / 255.0)
                labels.append(label)
    if not images:
        raise ValueError(f"в {root} нет картинок: нужны папки ok/ и defect/")
    if len(set(labels)) < 2:
        raise ValueError("нужны оба класса: папка с браком (defect/) и без (ok/)")
    return torch.tensor(np.stack(images)).unsqueeze(1), torch.tensor(labels)


def make_model(channels=(8, 16, 32), image_size=64, dropout=0.3):
    """conv -> batch_norm -> relu -> max_pool на каждый размер каналов, затем flatten -> dropout -> linear (1 логит)."""
    layers, c_in = [], 1
    for c in channels:
        layers += [nn.Conv2d(c_in, c, kernel_size=3, padding=1), nn.BatchNorm2d(c), nn.ReLU(), nn.MaxPool2d(2)]
        c_in = c
    side = image_size // 2 ** len(channels)  # каждый max_pool делит сторону пополам
    return nn.Sequential(*layers, nn.Flatten(), nn.Dropout(dropout), nn.Linear(c_in * side * side, 1))


def train_model(X, y, *, epochs=20, channels=(8, 16, 32), use_class_weights=True, dropout=0.3, lr=3e-3,
                optimizer_cls=None, batch_size=32, seed=0, device="cpu"):
    """Обучить сеть на X (N, 1, H, W) в [0, 1] и y (N,). -> {model, mean, std, losses, pos_weight}."""
    torch.manual_seed(seed)
    X, y = torch.as_tensor(X, dtype=torch.float32), torch.as_tensor(y).long()
    mean, std = X.mean(dim=(0, 2, 3)), X.std(dim=(0, 2, 3))  # статистики каналов — только по train
    Xn = (X - mean[None, :, None, None]) / std[None, :, None, None]
    w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y.numpy())  # брак редкий — весит больше
    pos_weight = torch.tensor(w[1] / w[0] if use_class_weights else 1.0)
    model = make_model(channels, X.shape[-1], dropout).to(device)
    opt = (optimizer_cls or torch.optim.Adam)(model.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight.to(device))  # готовая взвешенная потеря по логитам
    loader = DataLoader(TensorDataset(Xn, y), batch_size=batch_size, shuffle=True, generator=torch.Generator().manual_seed(seed))
    losses = []
    for _ in range(epochs):  # стандартный цикл обучения torch
        model.train()
        total = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device).float().reshape(-1, 1)
            opt.zero_grad()
            value = loss_fn(model(xb), yb)
            value.backward()
            opt.step()
            total += value.item() * len(xb)
        losses.append(total / len(Xn))  # средняя на объект за эпоху
    return {"model": model, "mean": mean, "std": std, "losses": losses, "pos_weight": float(pos_weight)}


def run(data_root="data/images", *, test_size=0.2, threshold=0.5, seed=0, device="cpu", **train_kw):
    """Обучить на train, оценить на test. -> {recall, f1, pr_auc, confusion_matrix, losses, …}."""
    X, y = load_images(data_root)
    idx_tr, idx_te = train_test_split(np.arange(len(y)), test_size=test_size, random_state=seed, stratify=y.numpy())
    fit = train_model(X[idx_tr], y[idx_tr], seed=seed, device=device, **train_kw)
    model = fit["model"].eval()
    X_te = (X[idx_te] - fit["mean"][None, :, None, None]) / fit["std"][None, :, None, None]  # тест — статистиками train
    with torch.inference_mode():
        probs = torch.sigmoid(model(X_te.to(device))).reshape(-1).cpu().numpy()
    y_te = y[idx_te].numpy()
    y_pred = (probs >= threshold).astype(int)
    return {"recall": recall_score(y_te, y_pred, zero_division=0), "f1": f1_score(y_te, y_pred, zero_division=0),
            "pr_auc": average_precision_score(y_te, probs), "confusion_matrix": confusion_matrix(y_te, y_pred, labels=[0, 1]),
            "losses": fit["losses"], "n_train": len(idx_tr), "n_test": len(idx_te), "defect_share": float(y.float().mean()),
            "image_shape": tuple(X.shape[1:]), "pos_weight": fit["pos_weight"], "model": model}


if __name__ == "__main__":
    res = run()
    print(f"recall {res['recall']:.3f} · f1 {res['f1']:.3f} · pr_auc {res['pr_auc']:.3f}")
    print("матрица ошибок [[TN, FP], [FN, TP]]:", res["confusion_matrix"].tolist())
    Path("results").mkdir(exist_ok=True)
    keep = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in res.items() if k != "model"}
    Path("results/metrics.json").write_text(json.dumps(keep, ensure_ascii=False, indent=2))
