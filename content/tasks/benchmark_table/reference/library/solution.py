"""benchmark_table через pandas: json_normalize разворачивает config в столбцы, sort_values — лучшие сверху."""
import numpy as np
import pandas as pd  # таблица результатов


def benchmark_table(results, sort_by="recall", ascending=False, round_to=None, params=True):
    """results: строки ablation [{"variant", "config", **метрики}] или {имя: {метрика: значение}}.
    Матрицы в таблицу не идут; params=True — настройки столбцами "param.<имя>"."""
    if isinstance(results, dict):
        results = [{"variant": name, **metrics} for name, metrics in results.items()]
    table = pd.json_normalize(list(results), sep=".")  # {"config": {"lr": …}} -> столбец "config.lr"
    if table.empty:
        raise ValueError("нет результатов для таблицы")
    if "variant" not in table:
        table.insert(0, "variant", None)
    table["variant"] = [v if isinstance(v, str) else f"#{i}" for i, v in enumerate(table["variant"])]  # безымянные — по номеру
    params_cols = [c for c in table.columns if c.startswith("config.")]
    metric_cols = [c for c in table.columns if c != "variant" and c not in params_cols and c != "config"
                   and table[c].map(lambda v: np.ndim(v) == 0 and isinstance(v, (int, float, np.number)) and not isinstance(v, bool)).all()]
    table = table[["variant", *metric_cols, *(params_cols if params else [])]]  # матрицы и пустой config — отбросить
    table = table.astype({c: float for c in metric_cols}).rename(columns=lambda c: "param." + c[7:] if c.startswith("config.") else c)
    if sort_by not in table.columns:
        raise ValueError(f"нет столбца «{sort_by}» для сортировки; есть: {list(table.columns)}")
    table = table.sort_values(sort_by, ascending=ascending, kind="mergesort").reset_index(drop=True)  # ничьи — в исходном порядке
    if round_to is not None:
        table = table.round({c: round_to for c in table.select_dtypes("number").columns})
    return table
