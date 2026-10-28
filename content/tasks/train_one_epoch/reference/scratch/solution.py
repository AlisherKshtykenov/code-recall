"""train_one_epoch — одна эпоха обучения: для каждого батча прямой проход, потеря, градиенты, шаг оптимизатора."""
import torch


def train_one_epoch(model, loader, loss, optimizer, device="cpu"):
    """Возвращает среднюю потерю на объект за эпоху. loss(y_pred, y_true) — любая функция потерь (слот loss),
    optimizer — любой оптимизатор со step() и zero_grad() (слот optimizer)."""
    model.train()  # включить dropout и обновление running-статистик batch_norm
    total, count = 0.0, 0
    for batch in loader:
        x, y = batch[0].to(device), batch[1].to(device)  # батч из DataLoader: (картинки, метки, …)
        optimizer.zero_grad()  # градиенты прошлого батча не должны складываться с новыми
        out = model(x)  # логиты (N, 1)
        y = y.to(out.dtype).reshape(out.shape)  # метки (N,) long -> float (N, 1): как выход модели
        value = loss(out, y)  # средняя потеря батча
        value.backward()  # градиенты по всем весам
        optimizer.step()  # шаг оптимизатора
        total += value.item() * len(x)  # .item(): число без графа — иначе память растёт с каждым батчем
        count += len(x)
    if count == 0:
        raise ValueError("loader пуст: не на чем обучать")
    return total / count  # средняя на объект (последний батч может быть меньше)
