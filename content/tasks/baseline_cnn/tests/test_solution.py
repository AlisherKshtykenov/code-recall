"""BaselineCNN против такой же сети на слоях torch.nn со скопированными весами: выход, градиенты, статистики."""
import pytest
import torch
from torch import nn

from solution import BaselineCNN


def reference(model):
    """nn.Sequential: (Conv2d, BatchNorm2d, ReLU, MaxPool2d) × N, Flatten, Dropout, Linear — с весами моей сети."""
    layers = []
    for b in model.blocks:
        c_out, c_in, k, _ = b.weight.shape
        conv, bn = nn.Conv2d(c_in, c_out, k, padding=b.padding), nn.BatchNorm2d(c_out)
        with torch.no_grad():
            conv.weight.copy_(b.weight); conv.bias.copy_(b.bias)
            bn.weight.copy_(b.bn_weight); bn.bias.copy_(b.bn_bias)
            bn.running_mean.copy_(b.running_mean); bn.running_var.copy_(b.running_var)
        layers += [conv, bn, nn.ReLU(), nn.MaxPool2d(b.pool)]
    fc = nn.Linear(model.features, 1)
    with torch.no_grad():
        fc.weight.copy_(model.fc_weight); fc.bias.copy_(model.fc_bias)
    return nn.Sequential(*layers, nn.Flatten(), nn.Dropout(model.p), fc).to(model.fc_weight.dtype)


def mine_params(model):
    out = []
    for b in model.blocks:
        out += [b.weight, b.bias, b.bn_weight, b.bn_bias]
    return out + [model.fc_weight, model.fc_bias]


def ref_params(ref):
    return [p for m in ref if isinstance(m, (nn.Conv2d, nn.BatchNorm2d, nn.Linear)) for p in (m.weight, m.bias)]


@pytest.mark.parametrize("channels, image_size, in_channels", [((16, 32, 64), 64, 1), ((8, 16), 32, 1), ((4, 8, 8), 16, 3), ((4,), 8, 2)])
@pytest.mark.parametrize("mode", ["train", "eval"])
def test_same_output_and_grads_as_nn(channels, image_size, in_channels, mode):
    torch.manual_seed(0)
    model = BaselineCNN(in_channels, channels, image_size, dropout=0.0 if mode == "train" else 0.5).double()
    ref = reference(model)
    model.train(mode == "train")
    ref.train(mode == "train")
    x = torch.randn(3, in_channels, image_size, image_size, dtype=torch.float64)
    out, want = model(x), ref(x)
    assert out.shape == (3, 1) and torch.allclose(out, want), f"логиты ({mode}) как у nn-сети"
    out.sum().backward()
    want.sum().backward()
    for i, (a, b) in enumerate(zip(mine_params(model), ref_params(ref))):
        assert torch.allclose(a.grad, b.grad), f"градиент параметра {i} как у nn-сети"


def test_running_stats_after_training_steps():
    torch.manual_seed(1)
    model = BaselineCNN(channels=(4, 8), image_size=16, dropout=0.0).double()
    ref = reference(model)
    for _ in range(3):
        x = torch.randn(4, 1, 16, 16, dtype=torch.float64)
        model.train()(x)
        ref.train()(x)
    bns = [m for m in ref if isinstance(m, nn.BatchNorm2d)]
    for b, bn in zip(model.blocks, bns):
        assert torch.allclose(b.running_mean, bn.running_mean) and torch.allclose(b.running_var, bn.running_var), "статистики блоков как у nn"


def test_dropout_only_in_train():
    torch.manual_seed(2)
    model = BaselineCNN(channels=(4,), image_size=8, dropout=0.9)
    x = torch.randn(2, 1, 8, 8)
    model.eval()
    assert torch.equal(model(x), model(x)), "eval: выход детерминирован (dropout выключен)"
    model.train()
    assert not torch.equal(model(x), model(x)), "train: dropout каждый раз новый"


def test_default_architecture_for_defects():
    model = BaselineCNN()
    assert model(torch.randn(8, 1, 64, 64)).shape == (8, 1), "64×64 серые картинки -> 1 логит"
    assert len(model.blocks) == 3 and model.features == 64 * 8 * 8, "3 блока: 64 -> 32 -> 16 -> 8, признаков 64·8·8"
    assert sum(p.numel() for p in model.parameters()) == sum(p.numel() for p in reference(model).parameters()), "весов столько же, сколько у nn-сети"


def test_too_small_image_is_error():
    with pytest.raises(ValueError):
        BaselineCNN(channels=(4, 8, 16, 32), image_size=8)


def test_learns_scratch_vs_clean():
    torch.manual_seed(3)
    x = torch.rand(32, 1, 16, 16) * 0.1
    y = torch.zeros(32, 1)
    x[:16, :, 8, :] = 1.0  # «царапина» — светлая полоса
    y[:16] = 1
    model = BaselineCNN(channels=(4, 8), image_size=16, dropout=0.0)
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    loss_fn = nn.BCEWithLogitsLoss()
    losses = []
    for _ in range(40):
        opt.zero_grad()
        loss = loss_fn(model(x), y)
        loss.backward()
        opt.step()
        losses.append(loss.item())
    assert losses[-1] < losses[0] * 0.5, f"на игрушечных данных потеря падает хотя бы вдвое: {losses[0]:.3f} -> {losses[-1]:.3f}"
