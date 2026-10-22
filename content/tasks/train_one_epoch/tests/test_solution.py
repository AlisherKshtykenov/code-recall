"""train_one_epoch: поведение на игрушечных моделях — режим train, zero_grad перед каждым backward,
один шаг на батч, средняя потерия по объектам, метки приводятся к форме выхода, потеря падает за эпохи."""
import pytest
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from solution import train_one_epoch


def toy_data(n=64, seed=0):
    g = torch.Generator().manual_seed(seed)
    X = torch.randn(n, 4, generator=g)
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).long()  # линейно разделимо
    return X, y


class Spy(nn.Module):
    """Запоминает режим (train/eval) на каждом батче."""

    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(4, 1)
        self.modes = []

    def forward(self, x):
        self.modes.append(self.training)
        return self.fc(x)


class CountingOptimizer:
    """Оборачивает настоящий оптимизатор: считает step/zero_grad и проверяет, что градиенты не накопились."""

    def __init__(self, params, model, X_batches):
        self.inner = torch.optim.SGD(params, lr=0.0)
        self.steps = self.zeros = 0

    def zero_grad(self):
        self.zeros += 1
        self.inner.zero_grad()

    def step(self):
        assert self.zeros == self.steps + 1, "перед каждым шагом — ровно один zero_grad"
        self.steps += 1
        self.inner.step()


def test_returns_mean_loss_per_sample_with_uneven_last_batch():
    torch.manual_seed(0)
    X, y = toy_data(50)
    model = nn.Linear(4, 1)
    loader = DataLoader(TensorDataset(X, y), batch_size=16)  # 16 + 16 + 16 + 2
    loss_fn = nn.BCEWithLogitsLoss()
    want = loss_fn(model(X), y.float().view(-1, 1)).item()  # с lr = 0 веса не меняются — средняя по всем объектам
    got = train_one_epoch(model, loader, loss_fn, torch.optim.SGD(model.parameters(), lr=0.0))
    assert isinstance(got, float) and abs(got - want) < 1e-6, f"средняя потеря на объект {got:.6f} ≠ {want:.6f} (последний батч меньше)"


def test_switches_to_train_mode():
    X, y = toy_data(32)
    model = Spy()
    model.eval()
    train_one_epoch(model, DataLoader(TensorDataset(X, y), batch_size=8), nn.BCEWithLogitsLoss(), torch.optim.SGD(model.parameters(), lr=0.1))
    assert model.modes == [True] * 4 and model.training, "на всех батчах модель в режиме train (даже если до этого был eval)"


def test_one_step_and_zero_grad_per_batch():
    X, y = toy_data(40)
    model = nn.Linear(4, 1)
    opt = CountingOptimizer(model.parameters(), model, None)
    train_one_epoch(model, DataLoader(TensorDataset(X, y), batch_size=10), nn.BCEWithLogitsLoss(), opt)
    assert opt.steps == 4 and opt.zeros == 4, f"4 батча — 4 шага и 4 zero_grad, а было {opt.steps} и {opt.zeros}"


def test_grads_do_not_accumulate():
    X, y = toy_data(20)
    model = nn.Linear(4, 1)
    seen = []

    class Recorder(torch.optim.SGD):
        def step(self, closure=None):
            seen.append(model.weight.grad.clone())
            return super().step(closure)
    loader = DataLoader(TensorDataset(torch.cat([X[:10], X[:10]]), torch.cat([y[:10], y[:10]])), batch_size=10)  # два одинаковых батча
    train_one_epoch(model, loader, nn.BCEWithLogitsLoss(), Recorder(model.parameters(), lr=0.0))
    assert torch.allclose(seen[0], seen[1]), "на одинаковых батчах градиент одинаков — значит, он не накопился"


@pytest.mark.parametrize("y_dtype", [torch.long, torch.float32])
@pytest.mark.parametrize("y_shape", ["(N,)", "(N, 1)"])
def test_targets_adapted_to_output(y_dtype, y_shape):
    X, y = toy_data(16)
    y = y.to(y_dtype)
    if y_shape == "(N, 1)":
        y = y.view(-1, 1)
    model = nn.Linear(4, 1)
    loss = train_one_epoch(model, DataLoader(TensorDataset(X, y), batch_size=8), nn.BCEWithLogitsLoss(), torch.optim.SGD(model.parameters(), lr=0.1))
    assert loss > 0, "метки long или (N,) приводятся к float (N, 1) — как выход модели"


def test_loss_decreases_over_epochs():
    torch.manual_seed(1)
    X, y = toy_data(128)
    model = nn.Sequential(nn.Linear(4, 8), nn.ReLU(), nn.Linear(8, 1))
    loader = DataLoader(TensorDataset(X, y), batch_size=16, shuffle=True)
    opt, loss_fn = torch.optim.Adam(model.parameters(), lr=0.02), nn.BCEWithLogitsLoss()
    losses = [train_one_epoch(model, loader, loss_fn, opt) for _ in range(8)]
    assert losses[-1] < losses[0] * 0.6, f"за 8 эпох потеря падает: {[round(v, 3) for v in losses]}"


def test_works_with_any_loss_and_optimizer_objects():
    X, y = toy_data(16)
    model = nn.Linear(4, 1)
    loss = lambda pred, target: ((torch.sigmoid(pred) - target) ** 2).mean()  # noqa: E731  своя потеря (слот loss)
    assert train_one_epoch(model, DataLoader(TensorDataset(X, y), batch_size=4), loss, torch.optim.Adam(model.parameters())) >= 0


def test_moves_batches_to_device():
    X, y = toy_data(8)

    class DeviceCheck(nn.Linear):
        def forward(self, x):
            assert x.device.type == "cpu", "батч перенесён на device"
            return super().forward(x)
    model = DeviceCheck(4, 1)
    train_one_epoch(model, DataLoader(TensorDataset(X, y), batch_size=4), nn.BCEWithLogitsLoss(), torch.optim.SGD(model.parameters(), lr=0.1),
                    device=torch.device("cpu"))


def test_empty_loader_is_error():
    model = nn.Linear(4, 1)
    with pytest.raises(ValueError):
        train_one_epoch(model, [], nn.BCEWithLogitsLoss(), torch.optim.SGD(model.parameters(), lr=0.1))
