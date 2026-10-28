# adam (оптимизатор Adam)

**Что делает.** Обновляет веса сети по градиентам, подбирая шаг для каждого веса отдельно: где градиент стабильно большой — шаг осторожнее, где маленький и шумный — смелее. Почти всегда работает «из коробки», поэтому это оптимизатор по умолчанию.

## Как применять

### Как это делают в жизни

```python
import torch

opt = torch.optim.Adam(model.parameters(), lr=1e-3)      # оптимизатор на все веса модели
for images, targets in loader:
    opt.zero_grad()                                       # сбросить градиенты прошлого шага
    loss = loss_fn(model(images), targets)                # прямой проход и потеря
    loss.backward()                                       # градиенты
    opt.step()                                            # шаг Adam

torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)  # «правильная» регуляризация весов
torch.optim.Adam([{"params": model.backbone.parameters(), "lr": 1e-4},   # свой lr у части сети
                  {"params": model.head.parameters()}], lr=1e-3)
```


### Параметры `torch.optim.Adam`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `params` | — | `model.parameters()`, список тензоров или список групп-словарей со своими настройками |
| `lr` | `1e-3` | learning rate (скорость обучения) |
| `betas` | `(0.9, 0.999)` | сглаживание градиента (β1) и его квадрата (β2) |
| `eps` | `1e-8` | добавка к знаменателю, чтобы не делить на ноль |
| `weight_decay` | `0` | L2-регуляризация через градиент: g + wd·w |
| `amsgrad` | `False` | знаменатель не уменьшается (вариант AMSGrad) |
| `maximize` | `False` | идти вверх по функции |
| `decoupled_weight_decay` | `False` | weight decay напрямую по весам — это AdamW |

Не повторяем: `foreach`, `fused`, `capturable`, `differentiable` (ускорения и режимы для GPU/графов), `state_dict`/`load_state_dict`.


### Подводные камни

1. **`weight_decay` в Adam ≠ AdamW.** В Adam L2 идёт через адаптивный знаменатель и почти не работает; для регуляризации берите `AdamW` (или `decoupled_weight_decay=True`).
2. **Забытый `zero_grad`.** Градиенты складываются между backward — шаги становятся всё больше.
3. **lr для Adam и SGD разный.** 1e-3 для Adam — нормально, для SGD — мало; при переключении оптимизатора подбирайте lr заново.
4. **Новый оптимизатор — новое состояние.** Пересоздание `Adam` посреди обучения обнуляет m и v — первые шаги снова «с поправкой на ноль».


### Где используется на карте

<!-- map:start -->
- [classification](#/map/adam)
- [dimensionality_reduction](#/map/adam)
- [segmentation](#/map/adam)
- [face_recognition](#/map/adam)
- [time_series](#/map/adam)
- [text_to_speech](#/map/adam)
- [generative](#/map/adam)
- [defect_detection](#/map/adam) — оптимизатор baseline_cnn в стене
<!-- map:end -->


## Как работает

$$m \leftarrow \beta_1 m + (1-\beta_1)g, \quad v \leftarrow \beta_2 v + (1-\beta_2)g^2, \quad w \leftarrow w - \text{lr}\,\frac{m / (1-\beta_1^t)}{\sqrt{v / (1-\beta_2^t)} + \varepsilon}$$

**Идея.** Для каждого веса помним сглаженный градиент (куда идти) и сглаженный квадрат градиента (насколько он шумный); шаг — первое, делённое на корень второго.

$$m \leftarrow \beta_1 m + (1-\beta_1)g,\quad v \leftarrow \beta_2 v + (1-\beta_2)g^2,\quad w \leftarrow w - \text{lr}\,\frac{m/(1-\beta_1^t)}{\sqrt{v/(1-\beta_2^t)} + \varepsilon}$$

1. g = градиент (с `weight_decay` — g + wd·w; AdamW — уменьшить w напрямую).
2. Обновляем m и v, делим на поправки 1 − βᵗ (в начале m и v смещены к нулю).
3. Шаг w −= lr · m̂ / (√v̂ + eps); `amsgrad` — в знаменатель максимум из всех v.

## Задача

**Режим «Библиотека»** — примените `torch.optim.Adam` с той же сигнатурой, что в «С нуля»: тесты проверяют, что вызвано `Adam`. Это учит, как и где применять.

**Режим «С нуля»** — напишите класс `Adam` своими руками в `solution.py`: конструктор с теми же параметрами и проверками, `param_groups`, `state`, `step(closure=None)`, `zero_grad(set_to_none=True)`. Веса после любого числа шагов — как у `torch.optim.Adam`.
Можно операции над тензорами (`mul_`, `add_`, `addcmul_`, `addcdiv_`, `lerp_`, `sqrt`, `maximum`). Нельзя `torch.optim`.
В конце файла — `optimizer = Adam`: кирпичик реализует слот **optimizer**.

Общие тесты (сравнение с библиотекой на многих случаях) должны пройти оба режима.
