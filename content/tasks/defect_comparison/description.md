# Детекция дефектов: сравнение

**Задача.** Та же детекция брака, но вопрос другой: **что из цепочки реально помогает и хватает ли данных?** Стена берёт baseline целиком (кирпичик `baseline` — предыдущая стена) и проводит два эксперимента:

## Как применять

### Как это делают в жизни

```python
import pandas as pd
from sklearn.model_selection import learning_curve

rows = [{"variant": name, **train_and_eval(**{**base, **change})}       # ablation — цикл по вариантам
        for name, change in [("base", {}), ("без весов", {"weights": False}), ("sgd", {"opt": "sgd"})]]
pd.DataFrame(rows).sort_values("recall", ascending=False).to_csv("results/benchmark.csv")

sizes, tr, te = learning_curve(CNNClassifier(), X, y, train_sizes=[0.3, 0.6, 1.0], cv=3)  # обёртка с fit/predict/score
```

Нейросеть в sklearn-функции передают обёрткой с `fit` / `predict` / `score` — здесь это `CNNClassifier` (в жизни — `skorch.NeuralNetClassifier`).


### Как читать результат

- **Кривая test ещё растёт** на 100% — больше фото брака помогут сильнее, чем новая архитектура.
- **Вариант без детали не хуже base** (в пределах разброса) — деталь можно убрать. На тесте 12 бракованных одна ошибка — это 0.08 recall; для решений запускайте с `repeats=3`.
- **sgd с тем же числом эпох** обычно хуже adam: ему нужен больший lr и больше эпох (см. `sgd`).


### Режимы стены

- **«Всё эталоном»** — пишете только `compare.py`: эксперимент, таблица, графики.
- **«Всё сам»** — все кирпичики, включая стену `baseline`; сначала гоняются тесты каждого.


### Тесты

- в таблице 4 варианта, лучшие по recall сверху, есть метрики и настройки;
- каждый вариант меняет ровно одну деталь;
- метрики в [0, 1], base находит хотя бы половину брака;
- кривая обучения 3×3, recall на всех данных не ниже, чем на 30%;
- в `results/` — csv, md и два PNG; csv совпадает с таблицей;
- `CNNClassifier` ведёт себя как оценщик sklearn.


### Где используется на карте

<!-- map:start -->
- [defect_detection](#/map) — стена: какие детали помогают и хватает ли данных
<!-- map:end -->


## Как работает

1. **Ablation** — по одной детали от base (веса классов, adam, dropout 0.3):
   - без весов классов;
   - sgd вместо adam;
   - без dropout.
2. **Learning curve** — recall на 30%, 60% и 100% обучающих данных, 3 стратифицированных фолда.

Результат — `benchmark_table` по recall и графики в `results/`:

| Файл | Что внутри |
|---|---|
| `results/benchmark.csv`, `benchmark.md` | таблица вариантов: recall, f1, pr_auc, настройки |
| `results/ablation.png` | recall и f1 каждого варианта |
| `results/learning_curve.png` | кривая обучения: train и test, разброс по фолдам |

**Идея.** Два эксперимента над стеной baseline: что даёт каждая деталь (ablation) и хватает ли данных (learning curve).

1. ablation: base и три варианта по одной детали → таблица по recall → `results/benchmark.csv`, `ablation.png`.
2. CNN обёрнута в оценщик с fit / predict / score / get_params.
3. learning_curve: 30 / 60 / 100% train, 3 фолда → `results/learning_curve.png`.

## Задача

**Режим «Библиотека»** — сравнение на готовых инструментах: ablation циклом по вариантам с таблицей pandas, `sklearn.model_selection.learning_curve` (оценщик — наследник `BaseEstimator`, `ClassifierMixin`), таблица — `pd.json_normalize` + `sort_values`, оптимизаторы — `torch.optim`. Стена baseline подключается так же: `from bricks.baseline import …`.

**Режим «С нуля»** — на своих кирпичиках ablation, benchmark_table, learning_curve, adam, sgd.

Общие тесты (поведение и сравнение с библиотекой) должны пройти оба режима.
