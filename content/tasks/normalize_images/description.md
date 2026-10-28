# normalize_images (нормализация картинок)

**Что делает.** Приводит каждый канал картинки к среднему 0 и разбросу 1: из каждого пикселя вычитает среднее канала и делит на его стандартное отклонение. Так сеть учится быстрее и стабильнее. Среднее и std считают один раз по обучающему датасету.

## Как применять

### Как это делают в жизни

```python
import torch
import torchvision.transforms.v2 as T                     # современные трансформации torchvision
import torchvision.transforms.functional as TF            # они же функциями

# 1) mean/std по train (один раз, по всем пикселям каждого канала)
x = torch.stack([img for img, _ in train_ds])             # (N, C, H, W), float в [0, 1]
mean = x.mean(dim=(0, 2, 3))                              # среднее каждого канала
std = x.std(dim=(0, 2, 3), unbiased=False)                # разброс каждого канала

# 2) применяем к каждой картинке
transform = T.Compose([T.ToImage(), T.ToDtype(torch.float32, scale=True),  # uint8 0..255 -> float 0..1
                       T.Normalize(mean.tolist(), std.tolist())])         # (x - mean) / std
TF.normalize(img, mean.tolist(), std.tolist())            # то же самое для одного тензора
```

Для предобученных сетей (resnet, efficientnet) берут статистики ImageNet: `mean=[0.485, 0.456, 0.406]`, `std=[0.229, 0.224, 0.225]`.


### Параметры `torchvision.transforms.functional.normalize`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `tensor` | — | картинка `(..., C, H, W)`, только float (uint8 сначала переведите) |
| `mean` | — | среднее каждого канала: список, кортеж, число или тензор длины C |
| `std` | — | стандартное отклонение каждого канала; 0 — ошибка (деление на ноль) |
| `inplace` | `False` | `True` — изменить сам вход (экономит память, но ломает исходный тензор) |

`compute_mean_std(data, unbiased=False)` — в torchvision нет: принимает тензор `(N, C, H, W)` или DataLoader и считает по батчам (весь датасет в память не нужен).


### Подводные камни

1. **Статистики — только по train.** Mean/std по всему датасету — утечка из теста.
2. **Сначала float, потом normalize.** На uint8 0..255 `normalize` падает, а если забыть делить на 255 — mean/std ImageNet к данным не подходят.
3. **Один и тот же transform на train, валидации и инференсе.** Забытая нормализация на инференсе — тихая ошибка: сеть работает, но плохо.
4. **std по батчам ≠ std датасета.** Средние std батчей занижают разброс; считайте через суммы x и x² по всем пикселям.


### Где используется на карте

<!-- map:start -->
- [image_classification](#/map/normalize_images) — mean/std ImageNet для предобученных сетей
- [defect_detection](#/map/normalize_images) — серые 64×64: один канал, mean/std считаем по train
<!-- map:end -->


## Как работает

$$x'_{c,h,w} = \frac{x_{c,h,w} - \text{mean}_c}{\text{std}_c}$$

**Идея.** Сдвинуть и сжать значения каждого канала так, чтобы среднее стало 0, а разброс 1.

$$x' = \frac{x - \text{mean}_c}{\text{std}_c}, \qquad \text{std} = \sqrt{E[x^2] - E[x]^2}$$

1. По всем картинкам train и всем пикселям копим для каждого канала Σx, Σx² и число пикселей.
2. mean = Σx / n, var = Σx²/n − mean² (несмещённая — ×n/(n−1)), std = √var.
3. `normalize`: из пикселя вычитаем mean своего канала и делим на std (форма mean — (C, 1, 1)).

## Задача

**Режим «Библиотека»** — примените `torchvision.transforms.functional.normalize` с той же сигнатурой, что в «С нуля»: тесты проверяют, что вызвано `normalize`. Это учит, как и где применять.

**Режим «С нуля»** — напишите в `solution.py` две функции: `normalize(tensor, mean, std, inplace=False)` — та же сигнатура, тот же результат и те же ошибки, что у torchvision, и `compute_mean_std(data, unbiased=False)` — mean и std каждого канала по датасету.
Можно базовые операции torch (`sum`, умножение, `reshape`, `transpose`, `sqrt`). Нельзя `torchvision`, `torch.std`/`var`/`std_mean` и нормализующие слои.

Общие тесты (сравнение с библиотекой на многих случаях) должны пройти оба режима.
