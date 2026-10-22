# benchmark_table (сводная таблица экспериментов)

**Что делает.** Собирает результаты нескольких моделей или вариантов эксперимента в одну таблицу: строка — модель, столбец — метрика, лучшие сверху. Это то, что кладут в отчёт и по чему выбирают модель.

## Как это делают в жизни

```python
import pandas as pd

results = [{"variant": "baseline_cnn", "recall": 0.81, "f1": 0.70},
           {"variant": "resnet18", "recall": 0.88, "f1": 0.79}]
table = (pd.DataFrame(results)                       # список словарей -> таблица
           .sort_values("recall", ascending=False)   # лучшие по recall сверху
           .reset_index(drop=True))
table.round(3).to_markdown()                         # в README / отчёт
table.to_csv("results/benchmark.csv", index=False)   # в results/
```

В командах обычно ведут таблицы экспериментов в W&B или MLflow.

## Параметры (наша функция)

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `results` | — | строки `ablation` (`{"variant", "config", …метрики}`) или `{имя: {метрика: значение}}` |
| `sort_by` | `"recall"` | по какому столбцу сортировать |
| `ascending` | `False` | `False` — лучшие (большие) сверху |
| `round_to` | `None` | округлить числа |
| `params` | `True` | настройки варианта столбцами `param.<имя>` |

## Подводные камни

1. **Сортировка по одной метрике обманчива.** Лучший recall может быть у «всё — брак». Смотрите recall вместе с precision/f1 и pr_auc.
2. **Без разброса таблица врёт.** Добавьте `_std` (ablation с `repeats`), иначе 0.81 против 0.80 выглядит как победа.
3. **Матрицы ошибок не помещаются в ячейку** — их сохраняют отдельно (картинкой или csv).
4. **Одни и те же данные.** Строки сравнимы, только если тест один и тот же.

## Где используется на карте

<!-- map:start -->
- [face_recognition](#/map/benchmark_table)
- [text_to_speech](#/map/benchmark_table)
- [speech_recognition](#/map/benchmark_table)
- [defect_detection](#/map/benchmark_table) — baseline_cnn и варианты ablation — по recall
<!-- map:end -->

## Задача

Напишите `benchmark_table(results, sort_by="recall", ascending=False, round_to=None, params=True)` в `solution.py` → `pandas.DataFrame`.
Аналога нет — тесты проверяют поведение: сортировка (ничьи — в исходном порядке), столбцы, оба формата входа, матрицы не попадают, понятные ошибки.
