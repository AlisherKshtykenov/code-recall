"""ConvBlock против такого же блока на слоях torch.nn с теми же весами: выход, градиенты всех параметров,
running-статистики, режимы train/eval."""
import pytest
import torch
from torch import nn

from solution import ConvBlock


def reference(block):
    """nn.Conv2d -> nn.BatchNorm2d -> nn.ReLU -> nn.MaxPool2d с весами, скопированными из моего блока."""
    c_out, c_in, k, _ = block.weight.shape
    ref = nn.Sequential(nn.Conv2d(c_in, c_out, k, padding=block.padding), nn.BatchNorm2d(c_out, momentum=block.momentum, eps=block.eps),
                        nn.ReLU(), nn.MaxPool2d(block.pool)).to(block.weight.dtype)
    with torch.no_grad():
        ref[0].weight.copy_(block.weight)
        ref[0].bias.copy_(block.bias)
        ref[1].weight.copy_(block.bn_weight)
        ref[1].bias.copy_(block.bn_bias)
        ref[1].running_mean.copy_(block.running_mean)
        ref[1].running_var.copy_(block.running_var)
    return ref


def pairs(block, ref):
    return [(block.weight, ref[0].weight), (block.bias, ref[0].bias), (block.bn_weight, ref[1].weight), (block.bn_bias, ref[1].bias)]


@pytest.mark.parametrize("c_in, c_out, size", [(1, 8, 16), (3, 4, 10), (8, 16, 8), (2, 2, 7)])
@pytest.mark.parametrize("mode", ["train", "eval"])
def test_same_output_and_grads_as_nn(c_in, c_out, size, mode):
    torch.manual_seed(0)
    block = ConvBlock(c_in, c_out).double()
    with torch.no_grad():  # непустые статистики, чтобы eval проверял их использование
        block.running_mean.uniform_(-0.5, 0.5)
        block.running_var.uniform_(0.5, 2.0)
    ref = reference(block)
    block.train(mode == "train")
    ref.train(mode == "train")
    x = torch.randn(4, c_in, size, size, dtype=torch.float64)
    xa, xb = x.clone().requires_grad_(), x.clone().requires_grad_()
    out, want = block(xa), ref(xb)
    assert out.shape == want.shape and torch.allclose(out, want), f"выход ({mode}) как у nn-блока"
    up = torch.randn_like(out)
    out.backward(up)
    want.backward(up)
    assert torch.allclose(xa.grad, xb.grad), "градиент по входу как у nn-блока"
    for mine, theirs in pairs(block, ref):
        assert torch.allclose(mine.grad, theirs.grad), "градиенты весов как у nn-блока"


def test_running_stats_like_nn_over_several_steps():
    torch.manual_seed(1)
    block = ConvBlock(2, 4).double()
    ref = reference(block)
    block.train()
    ref.train()
    for _ in range(3):
        x = torch.randn(6, 2, 8, 8, dtype=torch.float64)
        block(x)
        ref(x)
    assert torch.allclose(block.running_mean, ref[1].running_mean) and torch.allclose(block.running_var, ref[1].running_var), \
        "running_mean / running_var после 3 шагов обучения как у nn.BatchNorm2d"


def test_eval_does_not_update_running_stats():
    block = ConvBlock(1, 3)
    block.eval()
    before = block.running_mean.clone(), block.running_var.clone()
    block(torch.randn(2, 1, 8, 8))
    assert torch.equal(block.running_mean, before[0]) and torch.equal(block.running_var, before[1]), "в eval статистики не меняются"


def test_shapes_and_parameters():
    block = ConvBlock(1, 16)
    assert block(torch.randn(8, 1, 64, 64)).shape == (8, 16, 32, 32), "64×64 -> 32×32, каналов 16"
    names = {n for n, _ in block.named_parameters()}
    assert names == {"weight", "bias", "bn_weight", "bn_bias"}, f"обучаемые параметры: {names}"
    assert {n for n, _ in block.named_buffers()} == {"running_mean", "running_var"}, "running-статистики — буферы (в state_dict, не в optimizer)"
    assert sum(p.numel() for p in block.parameters()) == sum(p.numel() for p in reference(block).parameters()), "столько же весов, сколько у nn-блока"


def test_trains_with_optimizer():
    torch.manual_seed(2)
    block = ConvBlock(1, 4)
    opt = torch.optim.Adam(block.parameters(), lr=0.05)
    x, target = torch.randn(8, 1, 8, 8), torch.rand(8, 4, 4, 4)
    first = None
    for _ in range(30):
        opt.zero_grad()
        loss = ((block(x) - target) ** 2).mean()
        loss.backward()
        opt.step()
        first = first if first is not None else loss.item()
    assert loss.item() < first, "блок обучается: потеря падает"


def test_state_dict_roundtrip():
    a, b = ConvBlock(2, 3), ConvBlock(2, 3)
    b.load_state_dict(a.state_dict())
    a.eval()
    b.eval()
    x = torch.randn(1, 2, 6, 6)
    assert torch.equal(a(x), b(x)), "state_dict сохраняет и веса, и running-статистики"
