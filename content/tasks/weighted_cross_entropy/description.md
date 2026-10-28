# weighted_cross_entropy (BCE по логитам с весом брака)

**Что делает.** Та же бинарная кросс-энтропия, что `log_loss`, но (1) принимает сырые логиты и сама применяет sigmoid — устойчиво при любых значениях; (2) умножает потерю на брак в `pos_weight` раз, чтобы редкий класс не «тонул» среди нормальных.

## Как применять

### Как это делают в жизни

```python
import torch
import torch.nn.functional as F
from sklearn.utils.class_weight import compute_class_weight

w = compute_class_weight("balanced", classes=[0, 1], y=y_train)      # [0.56, 5.0] при 10% брака
pos_weight = torch.tensor(w[1] / w[0])                               # 9.0 = отрицательных / положительных

logits = model(images).squeeze(1)                                    # сырые оценки, без sigmoid!
loss = F.binary_cross_entropy_with_logits(logits, targets.float(), pos_weight=pos_weight)
# то же слоем: torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
```


### Параметры `F.binary_cross_entropy_with_logits`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `input` | — | логиты (любые числа) |
| `target` | — | ответы той же формы, float (0/1 или мягкие метки) |
| `weight` | `None` | вес каждого элемента — умножает всю потерю |
| `reduction` | `"mean"` | `"mean"`, `"sum"`, `"none"` |
| `pos_weight` | `None` | вес положительного класса; тензор, broadcast по последней оси — можно свой вес на каждый выход (multilabel) |


### Подводные камни

1. **Не применяйте sigmoid перед этой потерей** — sigmoid уже внутри. Двойной sigmoid учится, но плохо и тихо.
2. **`pos_weight` ≠ вес брака из `class_weights`.** Нужен коэффициент `w[1] / w[0]` (= отрицательных / положительных), он умножает только положительные примеры.
3. **С весами вероятности смещены.** После обучения с `pos_weight = 9` `sigmoid(logit)` завышает вероятность брака — порог подбирайте на валидации.
4. **`target` — float той же формы.** `(N, 1)` логитов и `(N,)` меток — ошибка; делайте `.squeeze(1)` или `.unsqueeze(1)`.


### Где используется на карте

<!-- map:start -->
- [defect_detection](#/map/weighted_cross_entropy) — потеря для обучения baseline_cnn: pos_weight = отрицательных / положительных из class_weights
<!-- map:end -->


## Как работает

$$\ell(x, t) = -\big[w_+\,t \log\sigma(x) + (1 - t)\log(1 - \sigma(x))\big]$$

**Идея.** Та же кросс-энтропия, но sigmoid спрятан внутрь и посчитан устойчиво, а ошибки на положительном классе умножены на pos_weight.

$$\ell(x, t) = (1 - t)\,x + \big(1 + (w_+ - 1)\,t\big)\,\log(1 + e^{-x})$$

1. log(1 + e^(−x)) считаем через e^(−|x|) ≤ 1 — без переполнения.
2. Вес log-части: pos_weight для положительных примеров, 1 — для отрицательных.
3. Умножаем на `weight`, сворачиваем `reduction`.

### Устойчивость

$-\log\sigma(x) = \log(1 + e^{-x})$ при $x = -1000$ переполняет $e^{1000}$. Эталон считает через $e^{-|x|} \le 1$:

$$\log(1 + e^{-x}) = \log(1 + e^{-|x|}) + \max(-x, 0),$$

а $-|x|$ — через `where(x >= 0, -x, x)` (у `abs` в нуле градиент 0 — производная в нуле вышла бы неверной).


## Задача

**Режим «Библиотека»** — примените `torch.nn.functional.binary_cross_entropy_with_logits` с той же сигнатурой, что в «С нуля»: тесты проверяют, что вызвано `binary_cross_entropy_with_logits`; в `binary_cross_entropy_with_logits(…)` явно передайте `pos_weight=`. Это учит, как и где применять.

**Режим «С нуля»** — напишите `binary_cross_entropy_with_logits(input, target, weight=None, reduction="mean", pos_weight=None)` своими руками в `solution.py`: значения и градиенты как у torch, конечные при |x| = 1000.
Можно `exp`, `log1p`, `where`, арифметику. Нельзя `torch.nn`, `sigmoid`, `softplus`, `logsigmoid`, `logaddexp` и готовые кросс-энтропии.
В конце файла — `loss = binary_cross_entropy_with_logits`: кирпичик реализует слот **loss**.

Общие тесты (сравнение с библиотекой на многих случаях) должны пройти оба режима.
