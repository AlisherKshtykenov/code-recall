"""Сравнение «моя функция против библиотечной» для тестов: значение, тип ошибки и предупреждение должны совпадать."""
import warnings

import numpy as np


def call(f, *args, **kw):
    """(результат или имя ошибки, было ли предупреждение)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            value = f(*args, **kw)
        except (ValueError, TypeError, RuntimeError) as e:  # InvalidParameterError в sklearn — наследник ValueError
            value = next(n for t, n in ((ValueError, "ValueError"), (TypeError, "TypeError"), (RuntimeError, "RuntimeError")) if isinstance(e, t))
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
