"""Сравнение оптимизатора с torch.optim: одинаковые стартовые веса, одинаковые данные, N шагов -> одинаковые веса."""
import torch


def make_model(seed=0):
    torch.manual_seed(seed)
    return torch.nn.Sequential(torch.nn.Linear(4, 8), torch.nn.Tanh(), torch.nn.Linear(8, 1))


def data(seed=1, n=32):
    g = torch.Generator().manual_seed(seed)
    X = torch.randn(n, 4, generator=g)
    return X, X @ torch.tensor([[1.0], [-2.0], [0.5], [3.0]]) + 0.3 * torch.randn(n, 1, generator=g)


def train(opt_cls, steps=30, model_seed=0, groups=None, **kw):
    """Веса модели после steps шагов на одних и тех же данных."""
    model, (X, y) = make_model(model_seed), data()
    params = groups(model) if groups else model.parameters()
    opt = opt_cls(params, **kw)
    for _ in range(steps):
        opt.zero_grad()
        ((model(X) - y) ** 2).mean().backward()
        opt.step()
    return [p.detach().clone() for p in model.parameters()], opt


def assert_same_trajectory(mine_cls, torch_cls, steps=30, groups=None, **kw):
    mine, _ = train(mine_cls, steps, groups=groups, **kw)
    ref, _ = train(torch_cls, steps, groups=groups, **kw)
    for i, (a, b) in enumerate(zip(mine, ref)):
        assert torch.allclose(a, b, rtol=1e-5, atol=1e-6), f"параметр {i} после {steps} шагов отличается от torch ({kw}): max |Δ| = {(a - b).abs().max():.2e}"
