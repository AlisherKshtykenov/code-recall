"""sgd своими руками — как torch.optim.SGD: momentum, dampening, nesterov, weight_decay, maximize."""
import torch


def param_groups_from(params, defaults):
    """Как в torch.optim: список тензоров (или model.parameters()) — одна группа; список словарей — свои группы."""
    params = list(params)
    if len(params) == 0:
        raise ValueError("optimizer got an empty parameter list")
    if not isinstance(params[0], dict):
        params = [{"params": params}]
    groups = []
    for g in params:
        g = dict(g)
        ps = g["params"]
        g["params"] = [ps] if isinstance(ps, torch.Tensor) else list(ps)
        for key, value in defaults.items():
            g.setdefault(key, value)
        groups.append(g)
    return groups


class SGD:
    """Шаг против градиента: w = w − lr·g; с momentum — против сглаженного градиента (буфера скорости)."""

    def __init__(self, params, lr=1e-3, momentum=0, dampening=0, weight_decay=0, nesterov=False, *, maximize=False):
        if lr < 0.0:  # те же проверки и сообщения, что у torch
            raise ValueError(f"Invalid learning rate: {lr}")
        if momentum < 0.0:
            raise ValueError(f"Invalid momentum value: {momentum}")
        if weight_decay < 0.0:
            raise ValueError(f"Invalid weight_decay value: {weight_decay}")
        if nesterov and (momentum <= 0 or dampening != 0):
            raise ValueError("Nesterov momentum requires a momentum and zero dampening")
        self.defaults = dict(lr=lr, momentum=momentum, dampening=dampening, weight_decay=weight_decay,
                             nesterov=nesterov, maximize=maximize)
        self.param_groups = param_groups_from(params, self.defaults)
        self.state = {}  # для каждого веса: momentum_buffer

    def zero_grad(self, set_to_none=True):
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None:
                    continue
                if set_to_none:
                    p.grad = None
                else:
                    p.grad.detach_()
                    p.grad.zero_()

    @torch.no_grad()
    def step(self, closure=None):
        loss = None
        if closure is not None:
            with torch.enable_grad():
                loss = closure()
        for group in self.param_groups:
            lr, mom, damp, wd = group["lr"], group["momentum"], group["dampening"], group["weight_decay"]
            for p in group["params"]:
                if p.grad is None:
                    continue
                grad = p.grad if not group["maximize"] else -p.grad  # maximize — идти вверх
                if wd != 0:
                    grad = grad.add(p, alpha=wd)  # L2: g + wd·w
                if mom != 0:
                    st = self.state.setdefault(p, {})
                    buf = st.get("momentum_buffer")
                    if buf is None:
                        buf = grad.detach().clone()  # первый шаг: скорость = градиент
                        st["momentum_buffer"] = buf
                    else:
                        buf.mul_(mom).add_(grad, alpha=1 - damp)  # b = μ·b + (1 − dampening)·g
                    grad = grad.add(buf, alpha=mom) if group["nesterov"] else buf  # nesterov: «заглянуть вперёд»
                p.add_(grad, alpha=-lr)  # w = w − lr·g
        return loss


optimizer = SGD  # реализация слота optimizer
