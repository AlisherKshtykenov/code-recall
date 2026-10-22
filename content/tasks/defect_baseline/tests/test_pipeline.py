"""Стена «Детекция дефектов: baseline CNN»: формы данных и выхода, потеря падает, recall выше порога,
с весами классов recall выше, чем без."""
import warnings

import pytest
import torch

from pipeline import load_images, run

warnings.filterwarnings("ignore")  # UndefinedMetricWarning на коротких запусках, где брак ещё не найден


@pytest.fixture(scope="module")
def full():
    return run(seed=0)  # обычный запуск: 12 эпох


def test_data_shapes_and_defect_share(data_dir):
    X, y = load_images(str(data_dir / "images"))
    assert X.shape[1:] == (1, 64, 64) and X.dtype == torch.float32, f"картинки (N, 1, 64, 64) float, а не {tuple(X.shape)}"
    assert 0.0 <= X.min() and X.max() <= 1.0, "пиксели в [0, 1]"
    assert 0.05 < y.float().mean() < 0.2, f"брака ~10%, а не {y.float().mean():.2f}"


def test_model_output_shape(full):
    out = full["model"].eval()(torch.zeros(5, 1, 64, 64))
    assert out.shape == (5, 1), "по одному логиту брака на картинку"
    assert full["n_train"] + full["n_test"] == 600 and full["n_test"] == 120, "split 80/20"


def test_loss_decreases(full):
    losses = full["losses"]
    assert losses[-1] < losses[0] * 0.5, f"потеря падает хотя бы вдвое: {losses[0]:.3f} -> {losses[-1]:.3f}"


def test_recall_above_threshold(full):
    assert full["recall"] >= 0.6, f"recall {full['recall']:.2f} < 0.6: модель пропускает много брака"
    assert full["pr_auc"] >= 0.8, f"pr_auc {full['pr_auc']:.2f} < 0.8: брак плохо ранжируется"


def test_confusion_matrix_consistent(full):
    cm = full["confusion_matrix"]
    tp, fn = cm[1, 1], cm[1, 0]
    assert cm.sum() == full["n_test"] and abs(tp / (tp + fn) - full["recall"]) < 1e-9, "матрица ошибок согласована с recall"


@pytest.mark.parametrize("seed", [0, 1])
def test_class_weights_raise_recall(seed):
    # короткий бюджет (3 эпохи): без весов сеть сначала «учится» отвечать «норма» — это и показывает пользу весов
    with_w = run(seed=seed, epochs=3, use_class_weights=True)["recall"]
    without = run(seed=seed, epochs=3, use_class_weights=False)["recall"]
    assert with_w > without, f"с весами классов recall {with_w:.2f} должен быть выше, чем без них {without:.2f}"
