"""Контракт слота optimizer — верен для любой реализации (adam, sgd…)."""
import torch

from slots.optimizer import optimizer


def quadratic():
    w = torch.tensor([3.0, -2.0], requires_grad=True)
    return w, lambda: ((w - torch.tensor([1.0, 1.0])) ** 2).sum()


def test_step_decreases_loss():
    w, f = quadratic()
    opt = optimizer([w], lr=0.1)
    first = f().item()
    for _ in range(50):
        opt.zero_grad()
        f().backward()
        opt.step()
    assert f().item() < first, "за 50 шагов на квадратичной функции потери уменьшаются"


def test_step_changes_only_params_with_grad():
    a, b = torch.ones(2, requires_grad=True), torch.ones(2, requires_grad=True)
    opt = optimizer([a, b], lr=0.1)
    (a * 2).sum().backward()
    opt.step()
    assert not torch.equal(a.detach(), torch.ones(2)) and torch.equal(b.detach(), torch.ones(2)), "параметр без .grad не меняется"


def test_zero_grad_clears():
    w, f = quadratic()
    opt = optimizer([w], lr=0.1)
    f().backward()
    opt.zero_grad()
    assert w.grad is None or torch.all(w.grad == 0), "после zero_grad градиент сброшен"


def test_accepts_model_parameters_and_has_param_groups():
    model = torch.nn.Linear(3, 1)
    opt = optimizer(model.parameters(), lr=0.01)
    assert hasattr(opt, "param_groups") and len(opt.param_groups) >= 1, "у оптимизатора есть param_groups (как в torch.optim)"
    assert opt.param_groups[0]["lr"] == 0.01, "lr лежит в param_groups[0]['lr']"
