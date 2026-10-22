"""Карта навыков из combinations.csv: строки — типы задач, столбцы — категории, ячейки — кирпичики.

Разбор ячейки:
  «,»      — разные кирпичики;   «a / b» — варианты одного слота;   «a + b» — используются вместе;
  «(...)»  — пояснение, не имя;  «нет»   — пусто.
Синонимы сводятся к одному каноническому имени (SYNONYMS); одинаковый кирпичик в разных строках — одна задача.
То, что нельзя написать функцией, — «концепт» (только README, без эталона и тестов, на FSRS не влияет)."""
import csv
import io
import re

CATEGORIES = ["models", "preprocessing", "layers", "activations", "losses", "optimizers", "metrics", "comparison"]
CSV_COLUMNS = {"модели": "models", "preprocessing": "preprocessing", "layers": "layers", "activations": "activations",
               "losses": "losses", "optimizers": "optimizers", "metrics": "metrics", "comparison": "comparison"}
CATEGORY_TITLE = {"models": "Models", "preprocessing": "Preprocessing", "layers": "Layers", "activations": "Activations",
                  "losses": "Losses", "optimizers": "Optimizers", "metrics": "Metrics", "comparison": "Comparison"}
# дерево тем: ML → Данные / Нейросети / Обучение / Оценка / Проекты
TOPIC_OF = {"preprocessing": "ML/Данные/Preprocessing", "layers": "ML/Нейросети/Layers",
            "activations": "ML/Нейросети/Activations", "models": "ML/Нейросети/Models",
            "losses": "ML/Обучение/Losses", "optimizers": "ML/Обучение/Optimizers",
            "metrics": "ML/Оценка/Metrics", "comparison": "ML/Оценка/Comparison"}
PROJECTS_TOPIC = "ML/Проекты"
# категории, где кирпичики взаимозаменяемы через слот (сигнатуры слотов — из цепочки defect_detection)
SLOT_OF = {"activations": "activation", "losses": "loss", "optimizers": "optimizer", "metrics": "metric"}

# (категория, текст после снятия скобок) или просто текст -> каноническое имя
SYNONYMS = {
    # preprocessing
    "scaling": "standard_scaler", "scaling в [-1,1]": "minmax_scaler", "missing": "simple_imputer",
    "encoding": "one_hot_encoder", "imbalance": "class_weights", "outliers": "iqr_outliers",
    "normalization картинок": "normalize_images", "splitting": "train_test_split",
    "splitting по людям": "group_kfold", "transformation": "differencing",
    "нормализация текста": "text_normalization", "аудио": "mel_spectrogram", "аудио признаки": "mel_spectrogram",
    ("preprocessing", "encoding (токены)"): "tokenizer", ("preprocessing", "missing (ffill)"): "forward_fill",
    # layers
    "dense": "linear", "sigmoid на выходе": "sigmoid", "conv": "conv2d", "pooling": "max_pool2d", "residual": "residual_block",
    "attention": "attention", "recurrent": "lstm_layer", "conv_transpose": "conv_transpose2d",
    # losses
    ("losses", "focal"): "focal_loss", ("losses", "hinge"): "hinge_loss", ("losses", "likelihood"): "log_likelihood",
    ("losses", "reconstruction"): "reconstruction_error", ("losses", "dice"): "dice_loss", ("losses", "triplet"): "triplet_loss",
    ("losses", "arcface"): "arcface_loss", ("losses", "contrastive"): "contrastive_loss", ("losses", "mel_spectrogram"): "mel_loss",
    ("losses", "adversarial"): "adversarial_loss", ("losses", "diffusion"): "diffusion_loss", ("losses", "ctc"): "ctc_loss",
    # metrics
    ("metrics", "dice"): "dice_score", "r2": "r2", "reconstruction error": "reconstruction_error",
    "accuracy верификации": "accuracy", "mel-ошибка": "mel_loss",
    # comparison
    "cross_validation": "cross_val_score", "dummy_mean": "dummy_regressor", "dummy_most_frequent": "dummy_classifier",
    "stratified cv": "stratified_kfold", "mcnemar": "mcnemar_test", "silhouette по k": "silhouette_by_k",
    "ablation по размеру": "ablation", "leaderboard": "benchmark_table",
}
# не функция: только README
CONCEPTS = {"бустинг по деревьям": "boosting_trees", "итерации em": "em_iterations", "second_order": "second_order",
            "smo": "smo", "mos": "mos", "scratch vs pretrained": "scratch_vs_pretrained", "simple_model": "naive_forecast"}
# до разбора: «sgd+momentum» — это один SGD с параметром momentum, а не два кирпичика
PRE = {"sgd+momentum": "sgd (momentum)"}
# в слотовой категории, но не вариант слота: расписания learning rate (scheduler), к оптимизатору добавляются «+»
NOT_SLOT = {"cosine_annealing", "warmup"}
# что это (одной фразой) и связанные кирпичики — для README запланированных и подсказки на карте
NOTES = {"diffusion_loss": "MSE между настоящим шумом и шумом, который предсказала модель (обучение диффузионной модели)",
         "cosine_annealing": "расписание learning rate (scheduler) — добавляется к оптимизатору",
         "warmup": "расписание learning rate (scheduler): плавный рост lr в начале обучения",
         "sgd": "SGD, в т.ч. с momentum (параметр, а не отдельный кирпичик)",
         "mel_loss": "L1/L2 между mel-спектрограммами — и лосс, и метрика «mel-ошибка»",
         "reconstruction_error": "ошибка восстановления входа (MSE) — и лосс автоэнкодера, и метрика"}
RELATED = {"diffusion_loss": ["diffusion"], "diffusion": ["diffusion_loss"], "arcface_loss": ["arcface"], "arcface": ["arcface_loss"],
           "dice_loss": ["dice_score"], "dice_score": ["dice_loss"], "recall": ["confusion_matrix"], "f1": ["confusion_matrix", "recall"],
           "weighted_cross_entropy": ["class_weights", "log_loss"], "stratified_split": ["train_test_split"]}
# пояснения в скобках, которые на самом деле и есть каноническое имя
NAME_IN_PARENS = {"group_kfold"}


def split_top(text: str, sep: str) -> list[str]:
    """Разделить по sep вне скобок."""
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += ch in "(["
        depth -= ch in ")]"
        if ch == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def canon(category: str, raw: str) -> tuple[str, str, str]:
    """(каноническое имя, тип, пояснение). тип: brick | model | concept."""
    note = " ".join(re.findall(r"\(([^)]*)\)", raw))
    bare = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    low = bare.lower()
    for key in ((category, raw.strip()), (category, bare), raw.strip(), bare, low):
        if key in CONCEPTS or (isinstance(key, str) and key.lower() in CONCEPTS):
            return CONCEPTS[key if key in CONCEPTS else key.lower()], "concept", note
        if key in SYNONYMS:
            return SYNONYMS[key], ("model" if category == "models" else "brick"), note
    if note in NAME_IN_PARENS:
        return note, "brick", bare
    name = re.sub(r"[^\w]+", "_", low).strip("_")
    return name, ("model" if category == "models" else "brick"), note


def parse_cell(category: str, cell: str) -> list[dict]:
    """Ячейка -> [{name, kind, raw, note, slot_group, together}]. slot_group — номер группы «a / b» внутри ячейки."""
    cell = (cell or "").strip().strip("“”\"")
    if not cell or cell.lower() == "нет" or cell.lower().startswith("нет "):
        return []
    out = []
    for k, v in PRE.items():
        cell = cell.replace(k, v)
    for gi, part in enumerate(split_top(cell, ",")):
        variants = split_top(part, "/")
        for v in variants:
            together = split_top(v, "+")
            for t in together:
                name, kind, note = canon(category, t)
                out.append({"name": name, "kind": kind, "raw": t, "note": note, "cell": part,
                            "slot_group": gi if len(variants) > 1 else None, "together": len(together) > 1})
    return out


def parse_csv(text: str) -> dict:
    """-> {rows: [{key, title, cells: {cat: [item…]}}], bricks: {name: {kind, categories, rows, raw}}}"""
    reader = list(csv.reader(io.StringIO(text.replace("“", '"').replace("”", '"'))))
    head = [h.strip().lower() for h in reader[0]]
    cols = {i: CSV_COLUMNS[h] for i, h in enumerate(head) if h in CSV_COLUMNS}
    rows, bricks, seen = [], {}, {}
    for r in reader[1:]:
        if not r or not r[0].strip():
            continue
        title = r[0].strip()
        key = re.sub(r"[^\w]+", "_", title.lower()).strip("_")
        n = seen[key] = seen.get(key, 0) + 1
        if n > 1:
            key = f"{key}_{n}"
        cells = {}
        for i, cat in cols.items():
            items = parse_cell(cat, r[i] if i < len(r) else "")
            cells[cat] = items
            for it in items:
                b = bricks.setdefault(it["name"], {"kind": it["kind"], "categories": [], "rows": [], "raw": []})
                if cat not in b["categories"]:
                    b["categories"].append(cat)
                if key not in b["rows"]:
                    b["rows"].append(key)
                if it["raw"] not in b["raw"]:
                    b["raw"].append(it["raw"])
                if it["slot_group"] is not None:
                    b["slot_variant"] = True
        rows.append({"key": key, "title": title, "cells": cells})
    return {"rows": rows, "bricks": bricks}
