# conv_block (conv → batch_norm → relu → max_pool)

**Что делает.** Стандартный «кирпич» свёрточной сети: свёртка находит узоры, batch_norm стабилизирует их масштаб, relu оставляет только «узор есть», max_pool уменьшает карту вдвое. Несколько таких блоков подряд видят сначала края, потом царапины и пятна целиком.

## Как это делают в жизни

```python
import torch.nn as nn

def conv_block(c_in, c_out):
    return nn.Sequential(
        nn.Conv2d(c_in, c_out, kernel_size=3, padding=1, bias=False),  # bias не нужен: его съест BatchNorm
        nn.BatchNorm2d(c_out),                                          # нормировка по батчу + running-статистики
        nn.ReLU(inplace=True),                                          # нелинейность
        nn.MaxPool2d(2),                                                # 64×64 -> 32×32
    )

block = conv_block(1, 16)
feats = block(images)        # (batch, 1, 64, 64) -> (batch, 16, 32, 32)
```

## Из чего собран

| Шаг | Кирпичик | Что делает |
|---|---|---|
| 1 | `conv2d` | 3×3, padding 1 — размер сохраняется |
| 2 | `batch_norm` | `training=self.training`: в train — по батчу, в eval — по running-статистикам |
| 3 | `relu` | обнуляет отрицательное |
| 4 | `max_pool2d` | окно 2 — карта вдвое меньше |

Веса — `nn.Parameter` (их видит оптимизатор), running-статистики — `register_buffer` (сохраняются в `state_dict`, переносятся `.to(device)`, но не обучаются).

## Подводные камни

1. **`training` берите из модуля.** `batch_norm(..., training=self.training)` — тогда `model.eval()` выключает обновление статистик во всех блоках сразу.
2. **Статистики — буферы, а не атрибуты.** Обычный тензор-атрибут не попадёт в `state_dict` и не переедет на GPU.
3. **Порядок BN и ReLU.** Классика — conv → BN → ReLU; ReLU перед BN даёт половину нулей в статистиках.
4. **Bias свёртки перед BN бесполезен** (вычитается средним) — в nn пишут `bias=False`. Здесь он оставлен, чтобы блок совпадал с `nn.Conv2d` по умолчанию.

## Где используется на карте

<!-- map:start -->
- [defect_detection](#/map) — строительный блок baseline_cnn (2–3 штуки подряд)
<!-- map:end -->

## Задача

Напишите `ConvBlock(nn.Module)` в `solution.py` на своих кирпичиках: `from bricks.conv2d import conv2d`, `bricks.batch_norm`, `bricks.relu`, `bricks.max_pool2d`.
Тесты собирают такой же блок из `nn.Conv2d`, `nn.BatchNorm2d`, `nn.ReLU`, `nn.MaxPool2d` с теми же весами: выход, градиенты всех параметров и running-статистики должны совпасть в train и eval.
Можно `nn.Module`, `nn.Parameter`, `register_buffer`, `nn.init`. Нельзя nn-слои и `torch.nn.functional`.
