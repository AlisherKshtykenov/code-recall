"""evaluate средствами torch: inference_mode (без графа и градиентов), torch.sigmoid; метрики — функции sklearn.metrics."""
import numpy as np
import torch


@torch.inference_mode()  # строже no_grad: тензоры без истории, быстрее на валидации
def evaluate(model, loader, metrics, score_metrics=None, threshold=0.5, device="cpu", loss=None):
    """metrics: {имя: f(y_true, метки)} — например sklearn.metrics.recall_score;
    score_metrics: {имя: f(y_true, вероятности)} — average_precision_score. -> {имя: значение}."""
    model.eval()  # dropout выключен, batch_norm — по накопленным статистикам
    logits, targets, losses = [], [], []
    for x, y, *_ in loader:
        x, y = x.to(device), y.to(device)
        out = model(x)  # логиты (N, 1)
        if loss is not None:
            losses.append(loss(out, y.to(out.dtype).reshape(out.shape)) * len(x))  # сумма потерь батча
        logits.append(out.reshape(-1).cpu())
        targets.append(y.reshape(-1).cpu())
    if not logits:
        raise ValueError("loader пуст: нечего оценивать")
    probs = torch.sigmoid(torch.cat(logits)).numpy()  # готовая сигмоида torch
    y_true = torch.cat(targets).numpy().astype(np.int64)
    y_pred = (probs >= threshold).astype(np.int64)  # метки по порогу
    result = {name: f(y_true, y_pred) for name, f in metrics.items()}
    result.update({name: f(y_true, probs) for name, f in (score_metrics or {}).items()})
    if loss is not None:
        result["loss"] = float(torch.stack(losses).sum() / len(y_true))  # средняя на объект
    return result
