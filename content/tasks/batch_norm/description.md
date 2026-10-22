# batch_norm (batch normalization)

**Что делает.** Нормирует каждый канал по текущему батчу: вычитает среднее и делит на разброс, затем умножает на обучаемый масштаб γ и прибавляет сдвиг β. Сеть учится быстрее и меньше зависит от инициализации. На инференсе использует не батч, а статистики, накопленные за обучение.

$$y = \gamma\,\frac{x - \mu_B}{\sqrt{\sigma_B^2 + \varepsilon}} + \beta, \qquad \mu_{run} \leftarrow (1 - m)\,\mu_{run} + m\,\mu_B$$

## Как это делают в жизни

```python
import torch.nn as nn
import torch.nn.functional as F

bn = nn.BatchNorm2d(num_features=16)          # γ, β и running_mean / running_var на 16 каналов
model.train(); y = bn(feats)                  # обучение: статистики батча + обновление running-статистик
model.eval();  y = bn(feats)                  # инференс: running-статистики, батч не нужен

F.batch_norm(feats, bn.running_mean, bn.running_var, bn.weight, bn.bias,
             training=True, momentum=0.1, eps=1e-5)  # то же функцией
```

## Параметры `torch.nn.functional.batch_norm`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `input` | — | `(N, C)`, `(N, C, L)`, `(N, C, H, W)`… — канал по оси 1 |
| `running_mean`, `running_var` | — | накопленные статистики `(C,)`; обновляются на месте при `training=True`; `None` — не копить |
| `weight`, `bias` | `None` | γ и β `(C,)`; `None` — без масштаба/сдвига |
| `training` | `False` | `True` — статистики батча; `False` — накопленные |
| `momentum` | `0.1` | доля нового батча в running-статистиках |
| `eps` | `1e-5` | добавка под корень, чтобы не делить на ноль |

## Подводные камни

1. **Забытый `model.eval()`.** На инференсе сеть нормирует по одной картинке (или маленькому батчу) — результаты «плавают». Всегда `eval()` перед валидацией.
2. **Две дисперсии.** Для нормировки — со смещением (делим на n), в `running_var` — несмещённая (n − 1). Перепутаете — eval разойдётся с train.
3. **Батч из одного объекта** в обучении — ошибка (нечего усреднять). При маленьких батчах (1–4) BatchNorm работает плохо: берут GroupNorm/LayerNorm.
4. **`momentum` наоборот.** В torch это доля **нового** батча (0.1), а не старой статистики, как в Keras (0.99).

## Где используется на карте

<!-- map:start -->
- [image_classification](#/map/batch_norm)
- [defect_detection](#/map/batch_norm) — после conv2d в conv_block: стабилизирует обучение маленькой сети
<!-- map:end -->

## Задача

Напишите `batch_norm(input, running_mean, running_var, weight=None, bias=None, training=False, momentum=0.1, eps=1e-5)` своими руками в `solution.py`: выход, градиенты по input, weight, bias и обновлённые running-статистики как у `F.batch_norm`.
Можно `mean`, арифметику, `sqrt`, `view`. Нельзя `torch.nn`, `var`/`std` и готовые нормализации.
