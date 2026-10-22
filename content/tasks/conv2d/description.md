# conv2d (свёртка 2D)

**Что делает.** Скользит маленьким окном (ядром, например 3×3) по картинке и в каждом месте считает взвешенную сумму пикселей. Каждое ядро учится находить свой узор — край, точку, царапину; выход — карта, где этот узор есть.

$$y[n, o, i, j] = b_o + \sum_{c}\sum_{u,v} w[o, c, u, v]\; x[n, c,\; i\cdot s + u\cdot d,\; j\cdot s + v\cdot d]$$

Размер выхода: $H_{out} = \left\lfloor \frac{H + 2p - d(k-1) - 1}{s} \right\rfloor + 1$.

## Как это делают в жизни

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

conv = nn.Conv2d(in_channels=1, out_channels=16, kernel_size=3, padding=1)  # 16 ядер 3×3 по серой картинке
feats = conv(images)                       # (batch, 1, 64, 64) -> (batch, 16, 64, 64): padding=1 сохраняет размер
F.conv2d(images, conv.weight, conv.bias, stride=1, padding=1)  # то же функцией
F.conv2d(x, w, padding="same")             # размер как у входа при любом ядре (только stride=1)
F.conv2d(x, w_dw, groups=x.shape[1])       # depthwise: у каждого канала своё ядро
```

## Параметры `torch.nn.functional.conv2d`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `input` | — | `(N, C_in, H, W)` или одна картинка `(C_in, H, W)` |
| `weight` | — | `(C_out, C_in / groups, kH, kW)` — ядра |
| `bias` | `None` | `(C_out,)` |
| `stride` | `1` | шаг окна (число или пара) — stride 2 уменьшает картинку вдвое |
| `padding` | `0` | нули по краям: число, пара, `"valid"` (= 0) или `"same"` (выход того же размера; лишний ряд — снизу/справа) |
| `dilation` | `1` | «дырявое» ядро: расстояние между пикселями окна — больше обзор без новых весов |
| `groups` | `1` | каналы делятся на группы, каждая сворачивается своими ядрами; `groups = C_in` — depthwise |

## Подводные камни

1. **Это кросс-корреляция.** В нейросетях ядро не переворачивают (в отличие от «математической» свёртки) — веса всё равно учатся.
2. **Размер выхода.** Без padding каждая свёртка 3×3 съедает по пикселю с края; после нескольких слоёв размер для `linear` надо пересчитать (или взять `padding=1`).
3. **`"same"` не работает со stride > 1** — torch бросает ошибку.
4. **Чётное ядро и `"same"`** — отступ несимметричный, центр смещён; обычно берут нечётные ядра.

## Где используется на карте

<!-- map:start -->
- [dimensionality_reduction](#/map/conv2d)
- [image_classification](#/map/conv2d)
- [segmentation](#/map/conv2d)
- [face_recognition](#/map/conv2d)
- [generative](#/map/conv2d)
- [defect_detection](#/map/conv2d) — первый слой каждого conv_block: ищет царапины и пятна
<!-- map:end -->

## Задача

Напишите `conv2d(input, weight, bias=None, stride=1, padding=0, dilation=1, groups=1)` своими руками в `solution.py`: выход и градиенты по input, weight, bias как у `F.conv2d`, при всех настройках и с теми же ошибками.
Можно `Tensor.unfold`, `einsum`/`matmul`, `reshape`, индексацию и присваивание в срез. Нельзя `torch.nn`, `F.unfold`/`fold` и готовые свёртки.
