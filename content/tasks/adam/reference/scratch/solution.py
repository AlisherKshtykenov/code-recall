"""adam своими руками — как torch.optim.Adam: те же параметры, те же значения весов после любого числа шагов."""
import math

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
            g.setdefault(key, value)  # чего нет в группе — из общих настроек
        groups.append(g)
    return groups


class Adam:
    """Адаптивный шаг для каждого веса: m — сглаженный градиент, v — сглаженный квадрат градиента."""

    def __init__(self, params, lr=1e-3, betas=(0.9, 0.999), eps=1e-8, weight_decay=0, amsgrad=False, *,
                 maximize=False, decoupled_weight_decay=False):
        if not 0.0 <= lr:  # те же проверки и сообщения, что у torch
            raise ValueError(f"Invalid learning rate: {lr}")
        if not 0.0 <= eps:
            raise ValueError(f"Invalid epsilon value: {eps}")
        if not 0.0 <= betas[0] < 1.0:
            raise ValueError(f"Invalid beta parameter at index 0: {betas[0]}")
        if not 0.0 <= betas[1] < 1.0:
            raise ValueError(f"Invalid beta parameter at index 1: {betas[1]}")
        if not 0.0 <= weight_decay:
            raise ValueError(f"Invalid weight_decay value: {weight_decay}")
        self.defaults = dict(lr=lr, betas=betas, eps=eps, weight_decay=weight_decay, amsgrad=amsgrad,
                             maximize=maximize, decoupled_weight_decay=decoupled_weight_decay)
        self.param_groups = param_groups_from(params, self.defaults)  # группы параметров со своими настройками
        self.state = {}  # для каждого веса: step, exp_avg (m), exp_avg_sq (v), max_exp_avg_sq (amsgrad)

    def zero_grad(self, set_to_none=True):
        """Сбросить градиенты перед следующим backward (иначе они складываются)."""
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None:
                    continue
                if set_to_none:
                    p.grad = None  # по умолчанию в torch — None (экономит память)
                else:
                    p.grad.detach_()
                    p.grad.zero_()

    @torch.no_grad()  # обновление весов — не часть графа вычислений
    def step(self, closure=None):
        loss = None
        if closure is not None:  # closure пересчитывает потерю и градиенты (нужно, например, для LBFGS)
            with torch.enable_grad():
                loss = closure()
        for group in self.param_groups:
            lr, (beta1, beta2), eps, wd = group["lr"], group["betas"], group["eps"], group["weight_decay"]
            for p in group["params"]:
                if p.grad is None:
                    continue  # у веса не было градиента — не трогаем (и состояние не заводим)
                grad = p.grad if not group["maximize"] else -p.grad  # maximize — идти вверх по функции
                st = self.state.setdefault(p, {})
                if not st:  # первый шаг: нули
                    st["step"] = 0
                    st["exp_avg"] = torch.zeros_like(p, memory_format=torch.preserve_format)
                    st["exp_avg_sq"] = torch.zeros_like(p, memory_format=torch.preserve_format)
                    if group["amsgrad"]:
                        st["max_exp_avg_sq"] = torch.zeros_like(p, memory_format=torch.preserve_format)
                st["step"] += 1
                if wd != 0:
                    if group["decoupled_weight_decay"]:
                        p.mul_(1 - lr * wd)  # AdamW: уменьшаем веса напрямую, не через градиент
                    else:
                        grad = grad.add(p, alpha=wd)  # L2 через градиент: g + wd·w
                m, v = st["exp_avg"], st["exp_avg_sq"]
                m.lerp_(grad, 1 - beta1)  # m = β1·m + (1 − β1)·g — сглаженный градиент (lerp = это же, но точнее)
                v.mul_(beta2).addcmul_(grad, grad, value=1 - beta2)  # v = β2·v + (1 − β2)·g² — сглаженный квадрат
                bias1 = 1 - beta1 ** st["step"]  # поправка: в начале m и v смещены к нулю
                bias2 = 1 - beta2 ** st["step"]
                if group["amsgrad"]:
                    torch.maximum(st["max_exp_avg_sq"], v, out=st["max_exp_avg_sq"])  # не даём знаменателю уменьшаться
                    denom = (st["max_exp_avg_sq"].sqrt() / math.sqrt(bias2)).add_(eps)
                else:
                    denom = (v.sqrt() / math.sqrt(bias2)).add_(eps)  # √v̂ + eps
                p.addcdiv_(m, denom, value=-lr / bias1)  # w = w − lr · m̂ / (√v̂ + eps)
        return loss


optimizer = Adam  # реализация слота optimizer
