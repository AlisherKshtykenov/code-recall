"""Adam против torch.optim.Adam: одинаковые веса после N шагов при любых настройках."""
import pytest
import torch

from likelib import call
from optimlib import assert_same_trajectory, train
from solution import Adam


@pytest.mark.parametrize("kw", [
    {},                                              # всё по умолчанию
    {"lr": 0.01}, {"lr": 0.1},
    {"betas": (0.5, 0.9)}, {"betas": (0.0, 0.99)},  # без сглаживания градиента
    {"eps": 1e-3},
    {"weight_decay": 0.1},                           # L2 через градиент
    {"weight_decay": 0.1, "decoupled_weight_decay": True},  # как AdamW
    {"amsgrad": True}, {"amsgrad": True, "weight_decay": 0.01},
    {"maximize": True},
    {"lr": 0.05, "betas": (0.8, 0.95), "eps": 1e-6, "weight_decay": 0.05, "amsgrad": True},
])
def test_same_weights_as_torch(kw):
    assert_same_trajectory(Adam, torch.optim.Adam, steps=30, **kw)


@pytest.mark.parametrize("steps", [1, 2, 5, 200])
def test_many_steps(steps):
    assert_same_trajectory(Adam, torch.optim.Adam, steps=steps, lr=0.01)


def test_param_groups_with_own_lr():
    groups = lambda m: [{"params": m[0].parameters(), "lr": 0.1}, {"params": m[2].parameters()}]  # noqa: E731
    assert_same_trajectory(Adam, torch.optim.Adam, groups=groups, lr=0.01)
    _, opt = train(Adam, steps=1, groups=groups, lr=0.01)
    assert [g["lr"] for g in opt.param_groups] == [0.1, 0.01], "у группы свой lr, остальное — из общих настроек"
    assert opt.param_groups[0]["betas"] == (0.9, 0.999), "недостающие настройки группы берутся из defaults"


def test_state_like_torch():
    _, mine = train(Adam, steps=7, lr=0.01, amsgrad=True)
    _, ref = train(torch.optim.Adam, steps=7, lr=0.01, amsgrad=True)
    for pm, pr in zip(mine.state.values(), ref.state.values()):
        assert int(pm["step"]) == int(pr["step"]) == 7, "счётчик шагов"
        for key in ("exp_avg", "exp_avg_sq", "max_exp_avg_sq"):
            assert torch.allclose(pm[key], pr[key], rtol=1e-5, atol=1e-8), f"state['{key}'] как у torch"


def test_param_without_grad_is_skipped():
    a, b = torch.ones(3, requires_grad=True), torch.ones(3, requires_grad=True)
    opt = Adam([a, b], lr=0.1)
    (a ** 2).sum().backward()
    opt.step()
    assert torch.equal(b.detach(), torch.ones(3)) and b not in opt.state, "у b нет .grad — он не меняется и состояния не получает"


@pytest.mark.parametrize("set_to_none", [True, False])
def test_zero_grad(set_to_none):
    w = torch.ones(2, requires_grad=True)
    opt, ref = Adam([w]), torch.optim.Adam([torch.ones(2, requires_grad=True)])
    (w * 3).sum().backward()
    opt.zero_grad(set_to_none=set_to_none)
    assert (w.grad is None) if set_to_none else torch.equal(w.grad, torch.zeros(2)), "zero_grad: None или нули, как попросили"


def test_grads_accumulate_without_zero_grad():
    w = torch.ones(1, requires_grad=True)
    (w * 2).sum().backward()
    (w * 2).sum().backward()
    assert w.grad.item() == 4.0  # поэтому перед каждым backward нужен zero_grad


def test_closure_returns_loss():
    w = torch.tensor([2.0], requires_grad=True)
    opt = Adam([w], lr=0.1)

    def closure():
        opt.zero_grad()
        loss = (w ** 2).sum()
        loss.backward()
        return loss
    assert opt.step(closure).item() == 4.0 and w.item() < 2.0, "step(closure) возвращает потерю и делает шаг"


def test_step_does_not_build_graph():
    w = torch.tensor([1.0], requires_grad=True)
    opt = Adam([w], lr=0.1)
    (w ** 2).sum().backward()
    opt.step()
    assert w.grad_fn is None and w.is_leaf, "обновление весов не попадает в граф (torch.no_grad)"


@pytest.mark.parametrize("kw", [{"lr": -1}, {"eps": -1e-8}, {"betas": (1.0, 0.9)}, {"betas": (0.9, -0.1)}, {"weight_decay": -0.1}])
def test_errors_like_torch(kw):
    p = [torch.zeros(1, requires_grad=True)]
    assert call(Adam, p, **kw)[0] == call(torch.optim.Adam, p, **kw)[0] == "ValueError", f"неверные настройки {kw} — ValueError"


def test_empty_params_is_error():
    assert call(Adam, [])[0] == call(torch.optim.Adam, [])[0] == "ValueError", "пустой список параметров — ValueError"
