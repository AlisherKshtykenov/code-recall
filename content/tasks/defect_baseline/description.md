# Детекция дефектов: baseline CNN

**Задача.** По серой фотографии изделия 64×64 решить: брак (царапина или пятно) или норма. Брака мало (~10%), поэтому важнее всего **recall** — не пропустить брак.

## Как применять

### Данные

- `data/images/` — синтетический датасет: 600 изделий, 60 с браком (половина — царапины, половина — пятна). Сделан `content/tools/make_defects.py`.
- **Свои данные:** «Подключить папку» (в панели файлов) → папка, в которой подпапки `ok/` и `defect/` (или `брак/`) с картинками любого размера: они приводятся к серым 64×64. Можно и вызвать `run("data/моя_папка")`.


### Как это делают в жизни

```python
from torchvision import datasets, transforms
from torch.utils.data import DataLoader
import torch

tf = transforms.Compose([transforms.Grayscale(), transforms.Resize((64, 64)), transforms.ToTensor(),
                         transforms.Normalize([mean], [std])])            # mean/std — по train
ds = datasets.ImageFolder("data/images", transform=tf)                  # папки = классы
model = BaselineCNN()                                                    # или resnet18 с новым последним слоем
loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(9.0))      # брак в 9 раз дороже
opt = torch.optim.Adam(model.parameters(), lr=3e-3)
# дальше — train_one_epoch по эпохам и evaluate на валидации
```


### Как решать эту стену

- **«Всё эталоном»** — пишете только `pipeline.py`, кирпичики подключаются скрыто. Учите саму цепочку: порядок split → статистики → нормализация, веса, цикл обучения, метрики.
- **«Всё сам»** — каждый кирпичик (21 файл в `bricks/`) пишется заново; при «Проверить» сначала гоняются их собственные тесты, и в отчёте видно, какой кирпичик упал.
- **Смешанно** — например, «пишу сам» только `weighted_cross_entropy` и `class_weights`, остальное эталоном.
- Слот **optimizer**: в сборке переключите adam ↔ sgd — тесты стены должны пройти и с тем, и с другим.


### Тесты

- данные: `(N, 1, 64, 64)`, пиксели в [0, 1], брака ~10%;
- выход модели `(N, 1)`, split 480 / 120;
- потеря за 20 эпох падает хотя бы вдвое;
- recall ≥ 0.6 и pr_auc ≥ 0.8 на тесте;
- матрица ошибок согласована с recall;
- с весами классов recall выше, чем без (на коротком бюджете в 3 эпохи, seed 0 и 1).


### Подводные камни

1. **Сначала split, потом mean/std.** Статистики по всем данным — утечка из теста.
2. **Метрика — recall, но смотрите и f1/pr_auc.** «Всё — брак» даёт recall 1.
3. **Тест маленький:** 12 бракованных — один пропуск меняет recall на 0.08. Сравнивайте варианты по нескольким seed (стена «сравнение»).
4. **Порог 0.5 после `pos_weight` смещён** к «браку» — подбирайте его на валидации.


### Где используется на карте

<!-- map:start -->
- [defect_detection](#/map) — стена: вся цепочка от картинок до метрик
<!-- map:end -->


## Как работает

```
data/images/{ok,defect}/*.png
  -> stratified_split (80/20, доли брака сохранены)
  -> compute_mean_std (по train) -> normalize
  -> class_weights -> pos_weight = отрицательных / положительных
  -> baseline_cnn (conv_block × 3 -> flatten -> dropout -> linear)
  -> train_one_epoch × 12 (weighted_cross_entropy, optimizer из слота: adam / sgd)
  -> evaluate: recall, f1, pr_auc, confusion_matrix
```

**Идея.** Вся цепочка от картинок до метрик, собранная из кирпичиков: разбить, нормализовать, учесть дисбаланс, обучить CNN, оценить.

1. Загрузить картинки из `ok/` и `defect/`, привести к серым 64×64 в [0, 1].
2. stratified_split → mean/std по train → normalize train и test.
3. class_weights → pos_weight; baseline_cnn; train_one_epoch × эпох с weighted_cross_entropy и оптимизатором из слота.
4. evaluate: recall, f1, pr_auc, confusion_matrix.

## Задача

Режим один — **«С нуля»**: у этой задачи нет готовой функции в библиотеке.
