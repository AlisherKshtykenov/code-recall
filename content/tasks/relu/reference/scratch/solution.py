"""relu своими руками — как torch.relu: max(0, x) поэлементно, с тем же градиентом (в нуле — 0)."""
import torch


def relu(input):
    """ReLU(x) = x при x > 0, иначе 0. Тот же dtype и форма; градиент — 1 при x > 0, иначе 0."""
    if not isinstance(input, torch.Tensor):  # как torch.relu: только тензоры
        raise TypeError(f"relu(): argument 'input' must be Tensor, not {type(input).__name__}")
    zero = torch.zeros((), dtype=input.dtype, device=input.device)  # ноль того же dtype (и для int-тензоров)
    # where(x <= 0, 0, x): NaN не <= 0, поэтому остаётся NaN (как в torch); −inf -> 0.
    # Градиент where идёт только в выбранную ветку: при x > 0 — 1, при x <= 0 (и в самом нуле) — 0.
    return torch.where(input <= 0, zero, input)


activation = relu  # реализация слота activation
