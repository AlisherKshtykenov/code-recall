# linear (полносвязный слой, dense)

**Что делает.** Каждый выход — взвешенная сумма всех входов плюс сдвиг. «Dense» (плотный) — каждый выход связан с каждым входом. Последний слой почти любой сети: признаки → оценки классов.

$$y = x W^\top + b$$

## Как это делают в жизни

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

layer = nn.Linear(in_features=128, out_features=1)  # веса (1, 128) и сдвиг (1,)
logit = layer(features)                              # (batch, 128) -> (batch, 1)
F.linear(features, layer.weight, layer.bias)         # то же функцией
```

## Параметры `torch.nn.functional.linear`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `input` | — | `(*, in_features)`: любые передние оси, последняя — признаки |
| `weight` | — | `(out_features, in_features)` — по строке на нейрон (или `(in_features,)`) |
| `bias` | `None` | `(out_features,)`; `None` — без сдвига |

У слоя `nn.Linear(in_features, out_features, bias=True)` веса по умолчанию инициализируются равномерно в ±1/√in_features.

## Подводные камни

1. **`W` транспонирована.** Веса хранятся как `(out, in)`, поэтому `x @ W.T`, а не `x @ W`. Перепутанная форма даёт ошибку «mat1 and mat2 shapes cannot be multiplied».
2. **Перед linear после свёрток нужен flatten:** `(batch, C, H, W)` → `(batch, C·H·W)`; `in_features` должен совпасть с `C·H·W`.
3. **Работает по последней оси:** вход `(batch, time, features)` даёт `(batch, time, out)` — это не ошибка, а broadcast.
4. **Bias и BatchNorm.** Перед `batch_norm` bias бесполезен (среднее вычитается) — ставят `bias=False`.

## Где используется на карте

<!-- map:start -->
- [regression](#/map/linear)
- [classification](#/map/linear)
- [dimensionality_reduction](#/map/linear)
- [face_recognition](#/map/linear)
- [time_series](#/map/linear)
- [defect_detection](#/map/linear) — последний слой baseline_cnn: признаки -> 1 логит брака
<!-- map:end -->

## Задача

Напишите `linear(input, weight, bias=None)` своими руками в `solution.py`: выход и градиенты по input, weight, bias как у `F.linear`.
Можно `torch.matmul`, `.t()`, сложение. Нельзя `torch.nn`, `addmm`, `bilinear`.
