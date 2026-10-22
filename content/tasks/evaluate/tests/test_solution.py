"""evaluate: метрики совпадают со sklearn на тех же предсказаниях, модель в eval, без градиентов, порог, батчи."""
import numpy as np
import pytest
import torch
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, recall_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from solution import evaluate

LABEL_METRICS = {"recall": recall_score, "f1": f1_score, "confusion_matrix": confusion_matrix}
SCORE_METRICS = {"pr_auc": average_precision_score}


def setup(n=60, seed=0):
    torch.manual_seed(seed)
    X = torch.randn(n, 4)
    y = (X[:, 0] + 0.3 * torch.randn(n) > 0.8).long()  # ~20% «брака»
    model = nn.Sequential(nn.Linear(4, 1))
    with torch.no_grad():
        model[0].weight.copy_(torch.tensor([[2.0, 0.1, 0.0, -0.1]]))
        model[0].bias.fill_(-1.0)
    return model, X, y


def expected(model, X, y, threshold=0.5):
    with torch.no_grad():
        p = torch.sigmoid(model(X)).reshape(-1).numpy()
    pred = (p >= threshold).astype(int)
    out = {k: f(y.numpy(), pred) for k, f in LABEL_METRICS.items()}
    out.update({k: f(y.numpy(), p) for k, f in SCORE_METRICS.items()})
    return out


@pytest.mark.parametrize("batch_size", [1, 7, 16, 60])
def test_metrics_match_sklearn(batch_size):
    model, X, y = setup()
    got = evaluate(model, DataLoader(TensorDataset(X, y), batch_size=batch_size), LABEL_METRICS, SCORE_METRICS)
    want = expected(model, X, y)
    assert set(got) == set(want), f"ключи словаря: {sorted(got)}"
    for k in want:
        assert np.allclose(got[k], want[k]), f"{k}: {got[k]} ≠ sklearn {want[k]} (батч {batch_size})"


@pytest.mark.parametrize("threshold", [0.1, 0.3, 0.5, 0.8])
def test_threshold(threshold):
    model, X, y = setup()
    got = evaluate(model, DataLoader(TensorDataset(X, y), batch_size=8), LABEL_METRICS, SCORE_METRICS, threshold=threshold)
    want = expected(model, X, y, threshold)
    assert np.isclose(got["recall"], want["recall"]) and np.array_equal(got["confusion_matrix"], want["confusion_matrix"]), \
        f"метки по порогу {threshold}: вероятность ≥ порога — брак"
    assert np.isclose(got["pr_auc"], want["pr_auc"]), "pr_auc от порога не зависит"


def test_model_in_eval_and_no_grads():
    model, X, y = setup()
    model.add_module("drop", nn.Dropout(0.9))
    model.train()
    a = evaluate(model, DataLoader(TensorDataset(X, y), batch_size=10), LABEL_METRICS, SCORE_METRICS)
    b = evaluate(model, DataLoader(TensorDataset(X, y), batch_size=10), LABEL_METRICS, SCORE_METRICS)
    assert not model.training, "после evaluate модель в eval"
    assert np.isclose(a["pr_auc"], b["pr_auc"]), "в eval dropout выключен: результат повторяется"
    assert all(p.grad is None for p in model.parameters()), "градиенты не считались (torch.no_grad)"


def test_targets_of_any_shape_and_dtype():
    model, X, y = setup()
    want = expected(model, X, y)
    for yy in (y, y.float(), y.view(-1, 1), y.view(-1, 1).float()):
        got = evaluate(model, DataLoader(TensorDataset(X, yy), batch_size=8), LABEL_METRICS, SCORE_METRICS)
        assert np.isclose(got["f1"], want["f1"]), f"метки {tuple(yy.shape)} {yy.dtype} обрабатываются одинаково"


def test_optional_loss():
    model, X, y = setup()
    loss_fn = nn.BCEWithLogitsLoss()
    got = evaluate(model, DataLoader(TensorDataset(X, y), batch_size=7), {}, loss=loss_fn)
    with torch.no_grad():
        want = loss_fn(model(X), y.float().view(-1, 1)).item()
    assert set(got) == {"loss"} and abs(got["loss"] - want) < 1e-6, "loss — средняя на объект по всей валидации"


def test_any_metric_callables():
    model, X, y = setup()
    got = evaluate(model, DataLoader(TensorDataset(X, y), batch_size=8), {"доля брака": lambda t, p: p.mean()})
    assert 0 <= got["доля брака"] <= 1, "метрика — любая функция f(y_true, y_pred)"


def test_empty_loader_is_error():
    model, _, _ = setup()
    with pytest.raises(ValueError):
        evaluate(model, [], LABEL_METRICS)
