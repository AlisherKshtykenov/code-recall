"""benchmark_table — сводная таблица экспериментов: по строке на модель или вариант, по столбцу на метрику,
лучшие сверху (по умолчанию — по recall)."""
import numbers

import numpy as np
import pandas as pd


def _scalar(v):
    return isinstance(v, (numbers.Number, np.generic)) and np.ndim(v) == 0  # число (в т.ч. numpy), а не матрица


def benchmark_table(results, sort_by="recall", ascending=False, round_to=None, params=True):
    """results: список строк ablation [{"variant", "config", **метрики}] или словарь {имя: {метрика: значение}}.
    Матрицы (confusion_matrix) в таблицу не идут. params=True — настройки варианта столбцами "param.<имя>"."""
    if isinstance(results, dict):
        results = [{"variant": name, **metrics} for name, metrics in results.items()]
    rows = []
    for r in results:
        row = {"variant": r.get("variant", f"#{len(rows)}")}
        row.update({k: float(v) for k, v in r.items() if k not in ("variant", "config") and _scalar(v)})  # только числа
        if params:
            row.update({f"param.{k}": v for k, v in (r.get("config") or {}).items()})  # настройки — для чтения таблицы
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        raise ValueError("нет результатов для таблицы")
    if sort_by not in table.columns:
        raise ValueError(f"нет столбца «{sort_by}» для сортировки; есть: {list(table.columns)}")
    table = table.sort_values(sort_by, ascending=ascending, kind="mergesort").reset_index(drop=True)  # ничьи — в исходном порядке
    if round_to is not None:
        num = table.select_dtypes("number").columns
        table[num] = table[num].round(round_to)
    return table
