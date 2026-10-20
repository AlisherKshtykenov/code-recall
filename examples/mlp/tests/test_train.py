from data_utils import load_points
from model import MLP
from train import train


def test_loss_decreases_in_20_steps(seed, data_dir):
    X, y = load_points(str(data_dir / "points.csv"))
    X, y = X[:64], y[:64]                  # маленький срез — тест быстрый
    losses = train(MLP(), X, y, steps=20)
    assert len(losses) == 20
    assert losses[-1] < losses[0]


def test_train_returns_floats(seed):
    X, y = load_points()
    losses = train(MLP(), X[:16], y[:16], steps=3)
    assert all(isinstance(v, float) for v in losses)
