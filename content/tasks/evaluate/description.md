# evaluate (оценка модели на валидации)

**Что делает.** Прогоняет модель по валидации без обучения, собирает логиты всех батчей, превращает их в вероятности и метки по порогу и считает метрики — словарь `{"recall": …, "f1": …, "pr_auc": …}`.

## Как применять

### Как это делают в жизни

Готовой функции в PyTorch нет: пишут цикл и считают метрики sklearn по склеенным предсказаниям (или копят в torchmetrics).

```python
import torch
from sklearn.metrics import recall_score, f1_score, average_precision_score, confusion_matrix

@torch.no_grad()                                   # без градиентов: быстрее и меньше памяти
def evaluate(model, loader, device):
    model.eval()                                   # dropout выкл., batch_norm по running-статистикам
    probs, ys = [], []
    for x, y in loader:
        probs.append(model(x.to(device)).sigmoid().cpu())  # вероятности брака
        ys.append(y)
    p, y = torch.cat(probs).view(-1).numpy(), torch.cat(ys).view(-1).numpy()
    pred = p >= 0.5                                # метки по порогу
    return {"recall": recall_score(y, pred), "f1": f1_score(y, pred),
            "pr_auc": average_precision_score(y, p), "cm": confusion_matrix(y, pred)}
```


### Параметры (наша функция)

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `model` | — | выход `(N, 1)` логитов |
| `loader` | — | батчи `(x, y, …)` |
| `metrics` | — | `{имя: f(y_true, y_pred)}` — по меткам (recall, f1, confusion_matrix — слот **metric**) |
| `score_metrics` | `None` | `{имя: f(y_true, вероятности)}` — по вероятностям (pr_auc) |
| `threshold` | `0.5` | вероятность ≥ порога — брак |
| `device` | `"cpu"` | куда переносить батчи |
| `loss` | `None` | если задана — в словаре ещё `"loss"` (средняя на объект) |


### Подводные камни

1. **Метрики — по всей валидации, а не средним по батчам.** Средний recall батчей ≠ recall всей выборки (особенно с редким браком).
2. **`model.eval()` + `torch.no_grad()`** — оба нужны: первое меняет поведение слоёв, второе — экономит память. Одно не заменяет другое.
3. **pr_auc — по вероятностям, recall — по меткам.** Перепутать — получить AP одной точки.
4. **Порог.** 0.5 — не закон: при весах классов вероятности смещены; порог подбирают на валидации и фиксируют для теста.


### Где используется на карте

<!-- map:start -->
- [defect_detection](#/map) — recall, f1, pr_auc, confusion_matrix на валидации
<!-- map:end -->


## Как работает

**Идея.** Без обучения собрать логиты всей валидации и посчитать метрики по всей выборке сразу.

1. `model.eval()` и `torch.no_grad()`.
2. Собрать логиты и метки всех батчей; вероятности — sigmoid.
3. Метки по порогу: вероятность ≥ threshold — брак.
4. Метрики по меткам и по вероятностям; если задана потеря — средняя на объект.

## Задача

**Режим «Библиотека»** — та же сигнатура на готовых средствах torch: `@torch.inference_mode()` вместо ручного отключения градиентов и `torch.sigmoid` вместо своего кирпичика; метрики по-прежнему передаются функциями (`sklearn.metrics.recall_score` и т. п.). Тесты проверяют, что вызваны `inference_mode` и `sigmoid`.

**Режим «С нуля»** — напишите `evaluate(model, loader, metrics, score_metrics=None, threshold=0.5, device="cpu", loss=None)` в `solution.py`; вероятности — через свой `from bricks.sigmoid import sigmoid`.
Тесты сравнивают результат с метриками sklearn на тех же предсказаниях и проверяют поведение: eval, без градиентов, порог, любые батчи и формы меток.

Общие тесты (поведение и сравнение с библиотекой) должны пройти оба режима.
