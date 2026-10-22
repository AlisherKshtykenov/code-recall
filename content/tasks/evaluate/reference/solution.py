"""evaluate — оценка модели на валидации: логиты всех батчей -> вероятности (sigmoid) -> метки по порогу -> метрики."""
import numpy as np
import torch

from bricks.sigmoid import sigmoid


@torch.no_grad()  # на валидации градиенты не нужны: быстрее и без лишней памяти
def evaluate(model, loader, metrics, score_metrics=None, threshold=0.5, device="cpu", loss=None):
    """metrics: {имя: f(y_true, y_pred_метки)} — recall, f1, confusion_matrix;
    score_metrics: {имя: f(y_true, вероятности)} — pr_auc, roc_auc. Возвращает словарь {имя: значение}."""
    model.eval()  # dropout выключен, batch_norm — по накопленным статистикам
    logits, targets = [], []
    total, count = 0.0, 0
    for batch in loader:
        x, y = batch[0].to(device), batch[1].to(device)
        out = model(x)  # логиты (N, 1)
        if loss is not None:
            total += loss(out, y.to(out.dtype).reshape(out.shape)).item() * len(x)  # средняя потеря на объект
        logits.append(out.reshape(-1).cpu())
        targets.append(y.reshape(-1).cpu())
        count += len(x)
    if count == 0:
        raise ValueError("loader пуст: нечего оценивать")
    probs = sigmoid(torch.cat(logits)).numpy()  # вероятности брака
    y_true = torch.cat(targets).numpy().astype(np.int64)  # настоящие метки 0/1
    y_pred = (probs >= threshold).astype(np.int64)  # метки по порогу
    result = {name: f(y_true, y_pred) for name, f in metrics.items()}  # метрики по меткам
    result.update({name: f(y_true, probs) for name, f in (score_metrics or {}).items()})  # метрики по вероятностям
    if loss is not None:
        result["loss"] = total / count
    return result
