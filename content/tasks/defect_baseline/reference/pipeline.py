"""Детекция дефектов: baseline CNN — вся цепочка на своих кирпичиках.
картинки -> stratified_split -> mean/std по train -> normalize -> class_weights -> baseline_cnn
-> train_one_epoch (weighted_cross_entropy, оптимизатор из слота) -> evaluate (recall, f1, pr_auc, confusion_matrix)."""
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, TensorDataset

from bricks.baseline_cnn import BaselineCNN
from bricks.class_weights import compute_class_weight
from bricks.confusion_matrix import confusion_matrix
from bricks.evaluate import evaluate
from bricks.f1 import f1_score
from bricks.normalize_images import compute_mean_std, normalize
from bricks.pr_auc import average_precision_score
from bricks.recall import recall_score
from bricks.stratified_split import stratified_split
from bricks.train_one_epoch import train_one_epoch
from bricks.weighted_cross_entropy import binary_cross_entropy_with_logits
from slots.optimizer import optimizer

POSITIVE = ("defect", "брак", "bad", "ng")  # как может называться папка с браком


def load_images(root="data/images", size=64):
    """<root>/ok/*.png и <root>/defect/*.png (подойдёт и ваша папка через «Подключить папку») -> X (N, 1, size, size), y (N,)."""
    root = Path(root)
    images, labels = [], []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        label = int(folder.name.lower() in POSITIVE)  # 1 — брак, 0 — норма
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
                continue
            img = Image.open(f).convert("L").resize((size, size))  # серая, одного размера
            images.append(np.asarray(img, dtype=np.float32) / 255.0)  # 0..255 -> 0..1
            labels.append(label)
    if not images:
        raise ValueError(f"в {root} нет картинок: нужны папки ok/ и defect/")
    if len(set(labels)) < 2:
        raise ValueError("нужны оба класса: папка с браком (defect/) и без (ok/)")
    return torch.tensor(np.stack(images)).unsqueeze(1), torch.tensor(labels)


def train_model(X, y, *, epochs=12, channels=(8, 16, 32), use_class_weights=True, dropout=0.3, lr=3e-3,
                optimizer_cls=None, batch_size=32, seed=0, device="cpu"):
    """Обучить baseline_cnn на готовых массивах X (N, 1, H, W) в [0, 1] и y (N,).
    -> {model, mean, std, losses, pos_weight}; mean/std — по этим X (это train)."""
    torch.manual_seed(seed)
    X, y = torch.as_tensor(X, dtype=torch.float32), torch.as_tensor(y).long()
    mean, std = compute_mean_std(X)  # статистики — только по train
    Xn = normalize(X, mean, std)
    w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y.numpy())  # брак редкий — весит больше
    pos_weight = torch.tensor(w[1] / w[0] if use_class_weights else 1.0)  # во сколько раз ошибка на браке дороже
    model = BaselineCNN(1, channels, X.shape[-1], dropout).to(device)
    opt = (optimizer_cls or optimizer)(model.parameters(), lr=lr)  # слот optimizer: adam по умолчанию, sgd — в сборке
    loss = lambda out, target: binary_cross_entropy_with_logits(out, target, pos_weight=pos_weight)  # noqa: E731
    loader = DataLoader(TensorDataset(Xn, y), batch_size=batch_size, shuffle=True, generator=torch.Generator().manual_seed(seed))
    losses = [train_one_epoch(model, loader, loss, opt, device) for _ in range(epochs)]
    return {"model": model, "mean": mean, "std": std, "losses": losses, "pos_weight": float(pos_weight)}


def run(data_root="data/images", *, test_size=0.2, threshold=0.5, seed=0, device="cpu", **train_kw):
    """Обучить baseline на train, оценить на test. -> {recall, f1, pr_auc, confusion_matrix, losses, …}.
    train_kw — настройки train_model: epochs, channels, use_class_weights, dropout, lr, optimizer_cls, batch_size."""
    X, y = load_images(data_root)
    X_tr, X_te, y_tr, y_te = stratified_split(X, y, test_size=test_size, random_state=seed, stratify=y.numpy())  # сначала split
    fit = train_model(X_tr, y_tr, seed=seed, device=device, **train_kw)
    X_te = normalize(X_te, fit["mean"], fit["std"])  # тест — статистиками train
    metrics = evaluate(fit["model"], DataLoader(TensorDataset(X_te, y_te), batch_size=256),
                       {"recall": recall_score, "f1": f1_score, "confusion_matrix": confusion_matrix},
                       {"pr_auc": average_precision_score}, threshold=threshold, device=device)
    return {**metrics, "losses": fit["losses"], "n_train": len(y_tr), "n_test": len(y_te), "defect_share": float(y.float().mean()),
            "image_shape": tuple(X.shape[1:]), "pos_weight": fit["pos_weight"], "model": fit["model"]}


if __name__ == "__main__":
    res = run()
    print(f"recall {res['recall']:.3f} · f1 {res['f1']:.3f} · pr_auc {res['pr_auc']:.3f}")
    print("матрица ошибок [[TN, FP], [FN, TP]]:", res["confusion_matrix"].tolist())
    Path("results").mkdir(exist_ok=True)
    keep = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in res.items() if k != "model"}
    Path("results/metrics.json").write_text(json.dumps(keep, ensure_ascii=False, indent=2))
