# relu

**Что делает.** Оставляет положительные числа как есть, а отрицательные заменяет нулём. Самая частая нелинейность в нейросетях: дешёвая и не «затухает» для больших значений.

## Как применять

### Как это делают в жизни

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

x = torch.tensor([-2.0, 0.0, 3.0])
torch.relu(x)                   # tensor([0., 0., 3.])
F.relu(x, inplace=False)        # то же; inplace=True перезапишет x (экономит память)
layer = nn.ReLU()               # как слой — для nn.Sequential
model = nn.Sequential(nn.Conv2d(1, 8, 3), nn.BatchNorm2d(8), nn.ReLU())
```


### Параметры

| Функция | Параметр | По умолчанию | Что значит |
|---|---|---|---|
| `torch.relu` | `input` | — | тензор любой формы и dtype (в т.ч. целый) |
| `F.relu` / `nn.ReLU` | `inplace` | `False` | изменить сам вход вместо нового тензора |


### Подводные камни

1. **«Мёртвые» нейроны.** Если вход нейрона всегда отрицателен, градиент всегда 0 и нейрон больше не учится. Помогают BatchNorm перед ReLU, меньший learning rate, LeakyReLU.
2. **Градиент в нуле — 0** (по соглашению torch). Ровно ноль встречается редко, но после ReLU+квантования — часто.
3. **`inplace=True` и autograd.** Перезапись тензора, нужного для backward, даёт ошибку «modified by an inplace operation».
4. **NaN проходит насквозь:** `relu(nan) = nan`. Не надейтесь, что ReLU «спрячет» NaN из предыдущего слоя.


### Где используется на карте

<!-- map:start -->
- [dimensionality_reduction](#/map/relu)
- [image_classification](#/map/relu)
- [segmentation](#/map/relu)
- [face_recognition](#/map/relu)
- [text_to_speech](#/map/relu)
- [speech_recognition](#/map/relu)
- [defect_detection](#/map/relu) — после каждого batch_norm в conv_block
<!-- map:end -->


## Как работает

$$\mathrm{ReLU}(x) = \max(0, x), \qquad \mathrm{ReLU}'(x) = \begin{cases}1, & x > 0\\0, & x \le 0\end{cases}$$

**Идея.** Пропустить положительное, обнулить отрицательное.

1. Где x ≤ 0 — ставим 0, иначе оставляем x (NaN остаётся NaN).
2. Градиент — 1 там, где x > 0, иначе 0 (в самом нуле — 0, как в torch).

## Задача

**Режим «Библиотека»** — примените `torch.relu` с той же сигнатурой, что в «С нуля»: тесты проверяют, что вызвано `relu`. Это учит, как и где применять.

**Режим «С нуля»** — напишите `relu(input)` своими руками в `solution.py`: те же значения, dtype и градиенты, что у `torch.relu` (в нуле градиент 0, NaN остаётся NaN, −inf → 0).
Можно сравнения, `torch.where`, `torch.zeros`. Нельзя `relu`, `clamp`, `maximum`, `max`, `torch.nn`.
В конце файла — `activation = relu`: кирпичик реализует слот **activation**.

Общие тесты (сравнение с библиотекой на многих случаях) должны пройти оба режима.
