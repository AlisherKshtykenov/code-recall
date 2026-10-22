# class_weights (веса классов при дисбалансе)

**Что делает.** Даёт каждому классу вес так, чтобы редкий класс (брак) влиял на обучение столько же, сколько частый. В режиме `"balanced"` вес обратно пропорционален размеру класса.

$$w_k = \frac{n_{\text{samples}}}{n_{\text{classes}} \cdot n_k}$$

При 90 нормальных и 10 бракованных деталях: $w_0 = 100 / (2 \cdot 90) ≈ 0.56$, $w_1 = 100 / (2 \cdot 10) = 5$ — брак весит в 9 раз больше.

## Как это делают в жизни

```python
import numpy as np
import torch
from sklearn.utils.class_weight import compute_class_weight  # готовая функция

y_train = np.array([0] * 90 + [1] * 10)                   # метки обучающей выборки (только train!)
w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y_train)  # [0.56, 5.0]

pos_weight = torch.tensor(w[1] / w[0])                    # 9.0 — для бинарной задачи с одним логитом
loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)  # ошибка на браке штрафуется в 9 раз сильнее
# многоклассовая задача: torch.nn.CrossEntropyLoss(weight=torch.tensor(w, dtype=torch.float32))
```

## Параметры `sklearn.utils.class_weight.compute_class_weight`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `class_weight` | — (обязательный) | `"balanced"` — по формуле выше; `dict` {класс: вес} — заданные веса, остальные 1; `None` — все 1 |
| `classes` | — (keyword) | классы, для которых нужны веса; результат в том же порядке. Должны включать все метки из `y` |
| `y` | — (keyword) | метки обучающей выборки |
| `sample_weight` | `None` | веса объектов: в `"balanced"` классы считаются по сумме весов, а не по числу объектов |

Сопутствующее: `sklearn.utils.class_weight.compute_sample_weight` — сразу вес каждого объекта; `class_weight="balanced"` в `LogisticRegression`, `SVC`, `RandomForestClassifier`.

## Подводные камни

1. **Только по train.** Веса, посчитанные по всей выборке, — утечка из теста. Считайте после `stratified_split`.
2. **`pos_weight` ≠ `w[1]`.** `BCEWithLogitsLoss(pos_weight=…)` умножает только положительные примеры, поэтому нужен коэффициент `w[1] / w[0]` (= negatives / positives), а не сам вес брака.
3. **Веса меняют вероятности.** После обучения с весами `predict_proba` завышает вероятность редкого класса: порог 0.5 уже не «естественный». Калибруйте или подбирайте порог на валидации.
4. **Класс без объектов** в `"balanced"` — ошибка. В маленьких фолдах кросс-валидации это частая беда — используйте стратификацию.

## Где используется на карте

<!-- map:start -->
- [classification](#/map/class_weights)
- [defect_detection](#/map/class_weights) — брака ~10% — вес брака в 9 раз больше, отсюда pos_weight для weighted_cross_entropy
<!-- map:end -->

## Задача

Напишите `compute_class_weight` своими руками в `solution.py` — та же сигнатура (`class_weight, *, classes, y, sample_weight=None`) и тот же результат, что у sklearn, включая ошибки.
Можно numpy и обычные циклы. Нельзя `sklearn`, `np.bincount`, `np.unique(..., return_counts=True)` — посчитайте классы сами.
