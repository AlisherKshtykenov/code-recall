"""ablation через pandas: все запуски — одна таблица (строка = вариант × повтор), среднее и разброс — groupby."""
import copy

import numpy as np
import pandas as pd  # таблица запусков и агрегаты


def ablation(build_fn, variants, *, base=None, repeats=1, seed_key="seed", seed=0, strict=True):
    """variants: {имя: {параметр: значение}}; первая строка — сам base ("base").
    repeats > 1 — разные seed, в метриках среднее и <метрика>_std. -> [{"variant", "config", **метрики}]."""
    base = dict(base or {})
    configs = {}
    for name, changes in [("base", {}), *variants.items()]:
        unknown = set(changes) - set(base)
        if strict and unknown:  # опечатка в имени параметра дала бы «эффект ноль»
            raise ValueError(f"вариант «{name}» меняет параметры, которых нет в base: {sorted(unknown)}")
        configs[name] = {**copy.deepcopy(base), **changes}  # base не меняем
    runs = pd.DataFrame([  # строка — один запуск: вариант, номер повтора, метрики
        {"variant": name, "run": r, **build_fn(**({**cfg, seed_key: seed + r} if repeats > 1 else cfg))}
        for name, cfg in configs.items() for r in range(repeats)])
    metric_cols = [c for c in runs.columns if c not in ("variant", "run")]
    numeric = [c for c in metric_cols if runs[c].map(np.isscalar).all()]  # числа можно усреднять; матрицы — нет
    grouped = runs.groupby("variant", sort=False)  # sort=False: порядок вариантов как во входе
    mean = grouped[numeric].mean()  # среднее по повторам
    std = grouped[numeric].std(ddof=0)  # разброс по повторам (как np.std)
    rows = []
    for name, cfg in configs.items():
        part = runs[runs["variant"] == name]
        row = {"variant": name, "config": cfg}
        for c in metric_cols:
            if repeats == 1:
                row[c] = part[c].iloc[0]  # один запуск — значение как есть
            elif c in numeric:
                row[c], row[f"{c}_std"] = float(mean.loc[name, c]), float(std.loc[name, c])
            else:
                row[c] = list(part[c])  # не числа — списком по запускам
        rows.append(row)
    return rows
