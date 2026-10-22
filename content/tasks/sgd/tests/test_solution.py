"""SGD против torch.optim.SGD: одинаковые веса после N шагов при любых настройках."""
import pytest
import torch

from likelib import call
from optimlib import assert_same_trajectory, train
from solution import SGD


@pytest.mark.parametrize("kw", [
    {},                                              # всё по умолчанию (lr = 1e-3)
    {"lr": 0.01}, {"lr": 0.1},
    {"lr": 0.05, "momentum": 0.9},
    {"lr": 0.05, "momentum": 0.9, "dampening": 0.5},
    {"lr": 0.05, "momentum": 0.9, "nesterov": True},
    {"lr": 0.05, "weight_decay": 0.1},
    {"lr": 0.05, "momentum": 0.9, "weight_decay": 0.01, "nesterov": True},
    {"lr": 0.01, "maximize": True},
    {"lr": 0.05, "momentum": 0.5, "maximize": True},
])
def test_same_weights_as_torch(kw):
    assert_same_trajectory(SGD, torch.optim.SGD, steps=30, **kw)


@pytest.mark.parametrize("steps", [1, 2, 5, 200])
def test_many_steps(steps):
    assert_same_trajectory(SGD, torch.optim.SGD, steps=steps, lr=0.01, momentum=0.9)


def test_param_groups_with_own_lr_and_momentum():
    groups = lambda m: [{"params": m[0].parameters(), "lr": 0.1, "momentum": 0.5}, {"params": m[2].parameters()}]  # noqa: E731
    assert_same_trajectory(SGD, torch.optim.SGD, groups=groups, lr=0.01, momentum=0.9)
    _, opt = train(SGD, steps=1, groups=groups, lr=0.01, momentum=0.9)
    assert [(g["lr"], g["momentum"]) for g in opt.param_groups] == [(0.1, 0.5), (0.01, 0.9)], "у группы свои настройки"


def test_momentum_buffer_like_torch():
    _, mine = train(SGD, steps=7, lr=0.01, momentum=0.9)
    _, ref = train(torch.optim.SGD, steps=7, lr=0.01, momentum=0.9)
    for pm, pr in zip(mine.state.values(), ref.state.values()):
        assert torch.allclose(pm["momentum_buffer"], pr["momentum_buffer"], rtol=1e-5, atol=1e-8), "state['momentum_buffer'] как у torch"


def test_plain_step_is_minus_lr_grad():
    w = torch.tensor([1.0, -2.0], requires_grad=True)
    (w * torch.tensor([3.0, 4.0])).sum().backward()
    SGD([w], lr=0.1).step()
    assert torch.allclose(w.detach(), torch.tensor([0.7, -2.4])), "без momentum: w = w − lr·g"


def test_param_without_grad_is_skipped():
    a, b = torch.ones(3, requires_grad=True), torch.ones(3, requires_grad=True)
    opt = SGD([a, b], lr=0.1, momentum=0.9)
    (a ** 2).sum().backward()
    opt.step()
    assert torch.equal(b.detach(), torch.ones(3)), "у b нет .grad — он не меняется"


@pytest.mark.parametrize("set_to_none", [True, False])
def test_zero_grad(set_to_none):
    w = torch.ones(2, requires_grad=True)
    opt = SGD([w], lr=0.1)
    (w * 3).sum().backward()
    opt.zero_grad(set_to_none=set_to_none)
    assert (w.grad is None) if set_to_none else torch.equal(w.grad, torch.zeros(2)), "zero_grad: None или нули"


def test_closure_returns_loss():
    w = torch.tensor([2.0], requires_grad=True)
    opt = SGD([w], lr=0.1)

    def closure():
        opt.zero_grad()
        loss = (w ** 2).sum()
        loss.backward()
        return loss
    assert opt.step(closure).item() == 4.0 and torch.isclose(w, torch.tensor([1.6])).all(), "step(closure): потеря и шаг w − 0.1·4"


@pytest.mark.parametrize("kw", [{"lr": -1}, {"momentum": -0.1}, {"weight_decay": -0.1}, {"nesterov": True},
                                {"momentum": 0.9, "dampening": 0.1, "nesterov": True}])
def test_errors_like_torch(kw):
    p = [torch.zeros(1, requires_grad=True)]
    assert call(SGD, p, **kw)[0] == call(torch.optim.SGD, p, **kw)[0] == "ValueError", f"неверные настройки {kw} — ValueError"


def test_empty_params_is_error():
    assert call(SGD, [])[0] == call(torch.optim.SGD, [])[0] == "ValueError"
