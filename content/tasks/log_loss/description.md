# log_loss (бинарная кросс-энтропия)

**Что делает.** Штрафует модель за уверенные ошибки: если брак, а модель сказала «вероятность брака 0.01», штраф огромный (−log 0.01 ≈ 4.6); если сказала 0.99 — почти ноль. Это главная потеря для «да / нет» и метрика качества вероятностей.

## Как применять

### Как это делают в жизни

```python
import torch
import torch.nn.functional as F
from sklearn.metrics import log_loss

probs = torch.sigmoid(model(images)).squeeze(1)       # вероятности брака
loss = F.binary_cross_entropy(probs, targets.float())  # потеря для обучения (targets — float!)
loss.backward()

# в обучении лучше сразу по логитам: устойчивее (см. weighted_cross_entropy)
loss = F.binary_cross_entropy_with_logits(logits, targets.float())

log_loss(y_true, y_proba)                              # sklearn: метрика на валидации (numpy)
log_loss(y_true, proba_3_classes)                      # многоклассовая: (n, n_classes)
```


### Параметры

**`F.binary_cross_entropy(input, target, weight=None, reduction="mean")`**

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `input` | — | вероятности в [0, 1] (не логиты!) |
| `target` | — | ответы той же формы и dtype (0/1 или «мягкие» метки) |
| `weight` | `None` | вес каждого элемента (broadcast к форме input) |
| `reduction` | `"mean"` | `"mean"`, `"sum"` или `"none"` — без свёртки |

`size_average`, `reduce` — устаревшие, вместо них `reduction`.

**`sklearn.metrics.log_loss(y_true, y_proba, *, normalize=True, sample_weight=None, labels=None)`**

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `y_true` | — | метки классов |
| `y_proba` | — | вероятность класса 1 `(n,)` или всех классов `(n, n_classes)` (столбцы — классы по возрастанию) |
| `normalize` | `True` | среднее по объектам; `False` — сумма |
| `sample_weight` | `None` | веса объектов |
| `labels` | `None` | все классы — нужно, если в `y_true` встретился только один |


### Подводные камни

1. **log(0).** torch обрезает `log` на −100 (потеря ≤ 100), sklearn — вероятности машинным эпсилоном dtype (у float32 он больше, чем у float64: результаты разные!).
2. **Градиент torch — своя формула** `(p − t) / max(p(1 − p), 1e−12)`, а не производная обрезанного логарифма: на краях она ±1e12. Поэтому эталон делает свой `torch.autograd.Function`.
3. **sigmoid + BCELoss неустойчивы.** Для обучения берите `BCEWithLogitsLoss` по логитам — это наш `weighted_cross_entropy`.
4. **Целые метки.** `targets` типа long дают ошибку «expected Float» — делайте `.float()`.


### Где используется на карте

<!-- map:start -->
- [classification](#/map/log_loss)
- [defect_detection](#/map/log_loss) — базовая потеря для «брак / не брак» по вероятности
<!-- map:end -->


## Как работает

$$\mathrm{BCE}(p, t) = -\big[t \log p + (1 - t)\log(1 - p)\big]$$

**Идея.** Штраф = −log(вероятности, которую модель дала правильному ответу): уверенная правильная — почти 0, уверенная ошибка — огромный штраф.

$$\mathrm{BCE}(p, t) = -\big[t \log p + (1 - t)\log(1 - p)\big]$$

1. log p и log(1 − p), обрезанные снизу на −100 (иначе log 0 = −∞).
2. Поэлементная потеря, умноженная на `weight`, свёрнутая `reduction`.
3. Градиент по p: (p − t) / max(p(1 − p), 1e−12) — по формуле torch.
4. sklearn-вариант: вероятности обрезаются машинным эпсилоном и берётся −среднее log P(настоящего класса).

## Задача

**Режим «Библиотека»** — примените `torch.nn.functional.binary_cross_entropy + sklearn.metrics.log_loss` с той же сигнатурой, что в «С нуля»: тесты проверяют, что вызвано `binary_cross_entropy`, `log_loss`; в `binary_cross_entropy(…)` явно передайте `reduction=`. Это учит, как и где применять.

**Режим «С нуля»** — напишите в `solution.py`:
- `binary_cross_entropy(input, target, weight=None, reduction="mean")` — значения, градиенты (в т.ч. на краях) и ошибки как у torch; для градиента — свой `torch.autograd.Function`;
- `log_loss(y_true, y_proba=None, *, normalize=True, sample_weight=None, labels=None)` — как sklearn (бинарная и многоклассовая).

Можно `torch.log`, `log1p`, `clamp`, numpy. Нельзя `torch.nn`, готовые кросс-энтропии и `sklearn`.
В конце файла — `loss = binary_cross_entropy`: кирпичик реализует слот **loss**.

Общие тесты (сравнение с библиотекой на многих случаях) должны пройти оба режима.
