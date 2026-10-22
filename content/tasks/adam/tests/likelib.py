"""Сравнение «моя функция против библиотечной» для тестов: значение, тип ошибки и предупреждение должны совпадать."""
import warnings

import numpy as np


def call(f, *args, **kw):
    """(результат или имя ошибки, было ли предупреждение)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            value = f(*args, **kw)
        except (ValueError, TypeError, RuntimeError, IndexError) as e:  # InvalidParameterError в sklearn — наследник ValueError
            value = next(n for t, n in ((ValueError, "ValueError"), (TypeError, "TypeError"), (IndexError, "IndexError"),
                                        (RuntimeError, "RuntimeError")) if isinstance(e, t))
    return value, bool(w)


def to_np(x):
    if hasattr(x, "detach"):  # torch.Tensor
        return x.detach().cpu().numpy()
    return np.asarray(x)


def close(a, b, rtol=1e-6, atol=1e-8) -> bool:
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, rtol, atol) for x, y in zip(a, b))
    a, b = to_np(a), to_np(b)
    return a.shape == b.shape and np.allclose(a.astype(float), b.astype(float), rtol=rtol, atol=atol, equal_nan=True)


def assert_like(mine, lib, *args, check_warning=True, rtol=1e-6, atol=1e-8, **kw):
    """mine(*args, **kw) ведёт себя как lib(*args, **kw)."""
    (got, warned_got), (want, warned_want) = call(mine, *args, **kw), call(lib, *args, **kw)
    where = f"(вход {args}, параметры {kw})"
    if isinstance(want, str) or isinstance(got, str):
        same = isinstance(want, str) and isinstance(got, str) and got == want
        assert same, f"библиотека: {want if isinstance(want, str) else 'результат'}, у вас: {got if isinstance(got, str) else 'результат'} {where}"
        return
    assert close(got, want, rtol, atol), f"результат {got!r} ≠ библиотеке {want!r} {where}"
    if check_warning:
        assert warned_got == warned_want, (f"предупреждение: у библиотеки {'есть' if warned_want else 'нет'}, "
                                           f"у вас {'есть' if warned_got else 'нет'} {where}")


def assert_grads_like(mine, lib, *args, rtol=1e-6, atol=1e-8, **kw):
    """Для слоёв: одинаковый выход, одинаковые градиенты по всем тензорам с requires_grad
    и одинаковые значения всех тензорных аргументов после вызова (например, running_mean в batch_norm)."""
    import torch

    def run(f):
        a = [x.detach().clone().requires_grad_(x.requires_grad) if isinstance(x, torch.Tensor) else x for x in args]
        k = {n: (v.detach().clone().requires_grad_(v.requires_grad) if isinstance(v, torch.Tensor) else v) for n, v in kw.items()}
        out = f(*a, **k)
        outs = out if isinstance(out, tuple) else (out,)
        diff = [o for o in outs if isinstance(o, torch.Tensor) and o.requires_grad]
        if diff:
            g = torch.Generator().manual_seed(0)  # один и тот же «градиент сверху» для обеих функций
            torch.autograd.backward(diff, [torch.randn(o.shape, generator=g, dtype=o.dtype) for o in diff])
        tensors = [x for x in a if isinstance(x, torch.Tensor)] + [v for v in k.values() if isinstance(v, torch.Tensor)]
        return outs, [t.grad for t in tensors], [t.detach() for t in tensors]

    (o1, g1, t1), (o2, g2, t2) = run(mine), run(lib)
    where = f"(параметры {kw})"
    assert len(o1) == len(o2), f"число выходов {len(o1)} ≠ {len(o2)} {where}"
    for a, b in zip(o1, o2):
        assert close(a, b, rtol, atol), f"выход отличается от torch {where}: max |Δ| = {abs(to_np(a).astype(float) - to_np(b).astype(float)).max() if to_np(a).shape == to_np(b).shape else 'форма ' + str(to_np(a).shape) + ' ≠ ' + str(to_np(b).shape)}"
    for i, (a, b) in enumerate(zip(g1, g2)):
        assert (a is None) == (b is None), f"градиент аргумента {i}: у torch {'нет' if b is None else 'есть'}, у вас {'нет' if a is None else 'есть'} {where}"
        if a is not None:
            assert close(a, b, rtol, atol), f"градиент аргумента {i} отличается от torch {where}: max |Δ| = {(a - b).abs().max():.2e}"
    for i, (a, b) in enumerate(zip(t1, t2)):
        assert close(a, b, rtol, atol), f"аргумент {i} после вызова отличается от torch (например, running stats) {where}"
