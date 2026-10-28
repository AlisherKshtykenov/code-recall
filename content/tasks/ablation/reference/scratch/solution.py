"""ablation — абляция: убрать или заменить по одной детали эксперимента и посмотреть, как меняются метрики.
build_fn(**config) обучает и оценивает модель по настройкам и возвращает словарь метрик."""
import copy

import numpy as np


def ablation(build_fn, variants, *, base=None, repeats=1, seed_key="seed", seed=0, strict=True):
    """variants: {имя: {параметр: значение}} — каждый вариант меняет base только в этих параметрах.
    Первая строка — сам base ("base"). repeats > 1 — несколько seed: в метриках среднее и <метрика>_std.
    Возвращает [{"variant": имя, "config": настройки, **метрики}] в порядке variants."""
    base = dict(base or {})
    rows = []
    for name, changes in [("base", {}), *variants.items()]:
        if strict:
            unknown = set(changes) - set(base)  # опечатка в имени параметра молча дала бы «эффект ноль»
            if unknown:
                raise ValueError(f"вариант «{name}» меняет параметры, которых нет в base: {sorted(unknown)}")
        config = {**copy.deepcopy(base), **changes}  # base не меняем — копия + изменения варианта
        runs = []
        for r in range(repeats):
            cfg = {**config, seed_key: seed + r} if repeats > 1 else config  # разные seed — разные запуски
            runs.append(build_fn(**cfg))
        metrics = {}
        for key in runs[0]:
            values = [run[key] for run in runs]
            if repeats > 1 and all(np.isscalar(v) for v in values):
                metrics[key] = float(np.mean(values))  # среднее по запускам
                metrics[f"{key}_std"] = float(np.std(values))  # и разброс
            else:
                metrics[key] = values[0] if repeats == 1 else values  # не числа (матрицы) — как есть / списком
        rows.append({"variant": name, "config": config, **metrics})
    return rows
