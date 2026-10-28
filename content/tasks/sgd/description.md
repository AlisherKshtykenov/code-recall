# sgd (стохастический градиентный спуск, momentum)

**Что делает.** Делает шаг против градиента: «спуститься чуть-чуть туда, где потеря меньше». С momentum (импульсом) копит скорость, как шар, катящийся с горки: проскакивает мелкие ямки и меньше дёргается от шума.

## Как применять

### Как это делают в жизни

```python
import torch

opt = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)     # классика для CNN
sched = torch.optim.lr_scheduler.StepLR(opt, step_size=30, gamma=0.1) # lr делить на 10 каждые 30 эпох
for epoch in range(90):
    for images, targets in loader:
        opt.zero_grad()                                               # сбросить градиенты
        loss_fn(model(images), targets).backward()                   # градиенты
        opt.step()                                                    # w = w − lr·b
    sched.step()
```


### Параметры `torch.optim.SGD`

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `params` | — | `model.parameters()`, список тензоров или групп-словарей |
| `lr` | `1e-3` | learning rate |
| `momentum` | `0` | импульс μ: доля прошлой скорости (обычно 0.9) |
| `dampening` | `0` | ослабление нового градиента в буфере |
| `weight_decay` | `0` | L2: g + wd·w |
| `nesterov` | `False` | импульс Нестерова: шаг по g + μ·b; нужен momentum > 0 и dampening = 0 |
| `maximize` | `False` | идти вверх |

Не повторяем: `foreach`, `fused`, `differentiable`, `state_dict`.


### Подводные камни

1. **lr больше, чем для Adam.** SGD с lr = 1e-3 (по умолчанию) почти не учит CNN — берут 0.01–0.1 и уменьшают по расписанию.
2. **Первый шаг с momentum** — просто градиент: буфер создаётся из него, а не из нуля (так в torch).
3. **Nesterov без momentum** — ошибка, а не «тихо выключится».
4. **SGD без расписания lr** обычно не доходит до лучшего качества: в конце обучения шаг надо уменьшать.


### Где используется на карте

<!-- map:start -->
- [regression](#/map/sgd)
- [classification](#/map/sgd)
- [face_recognition](#/map/sgd)
<!-- map:end -->


## Как работает

$$b \leftarrow \mu b + (1 - \text{dampening})\,g, \qquad w \leftarrow w - \text{lr}\cdot b \quad(\text{nesterov: } g + \mu b)$$

**Идея.** Шаг против градиента; с momentum — против накопленной «скорости», которая сглаживает шум.

$$b \leftarrow \mu b + (1 - \text{dampening})\,g, \qquad w \leftarrow w - \text{lr}\cdot b$$

1. g = градиент (+ wd·w при weight_decay; −g при maximize).
2. Первый шаг: b = g; дальше b = μ·b + (1 − dampening)·g.
3. Шаг: w −= lr·b (nesterov — lr·(g + μ·b)).

## Задача

**Режим «Библиотека»** — примените `torch.optim.SGD` с той же сигнатурой, что в «С нуля»: тесты проверяют, что вызвано `SGD`. Это учит, как и где применять.

**Режим «С нуля»** — напишите класс `SGD` своими руками в `solution.py`: те же параметры и проверки, `param_groups`, `state["momentum_buffer"]`, `step(closure=None)`, `zero_grad(set_to_none=True)`. Веса после любого числа шагов — как у `torch.optim.SGD`.
Можно операции над тензорами. Нельзя `torch.optim`.
В конце файла — `optimizer = SGD`: кирпичик реализует слот **optimizer**.

Общие тесты (сравнение с библиотекой на многих случаях) должны пройти оба режима.
