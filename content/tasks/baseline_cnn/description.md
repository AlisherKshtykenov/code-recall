# baseline_cnn (простая CNN для дефектов)

**Что делает.** Маленькая свёрточная сеть «брак / норма»: несколько conv_block уменьшают картинку и выделяют признаки, flatten разворачивает их в вектор, dropout борется с переобучением, linear выдаёт один логит. Вероятность брака — `sigmoid(логит)`. Это baseline (базовая модель): то, с чем сравнивают всё более сложное.

```
(N, 1, 64, 64) -conv_block-> (N, 16, 32, 32) -conv_block-> (N, 32, 16, 16) -conv_block-> (N, 64, 8, 8)
               -flatten-> (N, 4096) -dropout-> -linear-> (N, 1)
```

## Как это делают в жизни

```python
import torch.nn as nn

model = nn.Sequential(
    conv_block(1, 16), conv_block(16, 32), conv_block(32, 64),  # см. conv_block
    nn.Flatten(),                                               # (N, 64, 8, 8) -> (N, 4096)
    nn.Dropout(0.5),                                            # только в model.train()
    nn.Linear(64 * 8 * 8, 1),                                   # один логит: брак или нет
)
logits = model(images)                                          # (N, 1)
probs = logits.sigmoid()                                        # вероятности для порога и pr_auc
```

Для настоящих фото чаще берут предобученную сеть (`torchvision.models.resnet18(weights="DEFAULT")`) и меняют последний слой — на карте это `resnet`, `efficientnet`.

## Параметры (наша сеть)

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `in_channels` | `1` | 1 — серые картинки, 3 — RGB |
| `channels` | `(16, 32, 64)` | каналы каждого conv_block; число блоков = длина |
| `image_size` | `64` | сторона входной картинки — нужна, чтобы посчитать размер linear |
| `dropout` | `0.5` | вероятность dropout перед linear |

## Подводные камни

1. **Один логит, а не два.** Для «брак / норма» хватает одного выхода + `BCEWithLogitsLoss` (`weighted_cross_entropy`). Два выхода + softmax — то же самое, но с лишним параметром.
2. **Размер linear зависит от картинки.** Сменили 64 → 128 — `features` вырос в 4 раза. Для любого размера ставят `nn.AdaptiveAvgPool2d(1)` перед flatten.
3. **`model.eval()` перед валидацией** — иначе работает dropout, а batch_norm обновляет статистики на валидации.
4. **Baseline должен быть простым.** Если сложная модель не обгоняет его заметно — проблема в данных или постановке, а не в архитектуре.

## Где используется на карте

<!-- map:start -->
- [defect_detection](#/map/baseline_cnn) — базовая модель: с ней сравниваются resnet и efficientnet
<!-- map:end -->

## Задача

Напишите `BaselineCNN(nn.Module)` в `solution.py` на своих кирпичиках: `from bricks.conv_block import ConvBlock`, `bricks.flatten`, `bricks.dropout`, `bricks.linear`.
Тесты собирают такую же сеть из nn-слоёв со скопированными весами: логиты, градиенты всех параметров и running-статистики должны совпасть.
Можно `nn.Module`, `nn.ModuleList`, `nn.Parameter`, `nn.init`. Нельзя nn-слои, `torch.nn.functional`, `torchvision`.
