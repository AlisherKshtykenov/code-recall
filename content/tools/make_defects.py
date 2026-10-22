"""Синтетический датасет «изделия»: серые картинки 64×64, ~10% брака (царапина или пятно).
python content/tools/make_defects.py <папка> [--n 600] [--share 0.1] [--seed 0]
Структура — как у настоящих данных: <папка>/ok/*.png, <папка>/defect/*.png."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 64


def product(rng):
    """Изделие: светлая шайба с текстурой и неравномерным освещением на тёмном фоне."""
    yy, xx = np.mgrid[0:SIZE, 0:SIZE] / SIZE
    cx, cy, r = rng.uniform(0.45, 0.55, 2).tolist() + [rng.uniform(0.33, 0.42)]
    disc = ((xx - cx) ** 2 + (yy - cy) ** 2) < r ** 2
    light = 0.55 + 0.2 * (xx * rng.uniform(-1, 1) + yy * rng.uniform(-1, 1))  # градиент освещения
    texture = rng.normal(0, 0.035, (SIZE, SIZE))  # шероховатость поверхности
    img = np.where(disc, light + texture, 0.12 + rng.normal(0, 0.02, (SIZE, SIZE)))
    return img, disc, (cx, cy, r)


def scratch(img, disc, geo, rng):
    """Тонкая тёмная или светлая линия внутри изделия."""
    cx, cy, r = geo
    yy, xx = np.mgrid[0:SIZE, 0:SIZE] / SIZE
    angle = rng.uniform(0, np.pi)
    length = rng.uniform(0.35, 0.7) * r
    px, py = cx + rng.uniform(-0.4, 0.4) * r, cy + rng.uniform(-0.4, 0.4) * r
    dx, dy = np.cos(angle), np.sin(angle)
    t = (xx - px) * dx + (yy - py) * dy  # координата вдоль царапины
    d = np.abs(-(xx - px) * dy + (yy - py) * dx)  # расстояние до линии
    mask = (d < rng.uniform(0.008, 0.016)) & (np.abs(t) < length) & disc
    img[mask] += rng.choice([-1, 1]) * rng.uniform(0.25, 0.4)
    return img


def spot(img, disc, geo, rng):
    """Пятно: размытый тёмный или светлый круг внутри изделия."""
    cx, cy, r = geo
    yy, xx = np.mgrid[0:SIZE, 0:SIZE] / SIZE
    px, py = cx + rng.uniform(-0.5, 0.5) * r, cy + rng.uniform(-0.5, 0.5) * r
    s = rng.uniform(0.03, 0.06)
    blob = np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (2 * s ** 2))
    img += disc * blob * rng.choice([-1, 1]) * rng.uniform(0.25, 0.4)
    return img


def make(root, n=600, share=0.1, seed=0):
    rng = np.random.default_rng(seed)
    root = Path(root)
    for sub in ("ok", "defect"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    n_defect = int(round(n * share))
    labels = np.array([1] * n_defect + [0] * (n - n_defect))
    rng.shuffle(labels)
    for i, lab in enumerate(labels):
        img, disc, geo = product(rng)
        if lab:
            img = (scratch if rng.random() < 0.5 else spot)(img, disc, geo, rng)
        img = np.clip(img, 0, 1)
        Image.fromarray((img * 255).astype(np.uint8), mode="L").save(root / ("defect" if lab else "ok") / f"{i:04d}.png")
    return n_defect


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--share", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    print("брака:", make(a.root, a.n, a.share, a.seed), "из", a.n)
