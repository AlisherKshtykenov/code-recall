"""dropout: маска случайная, поэтому проверяем свойства — eval и p=0 ничего не меняют, доля нулей ≈ p,
выжившие умножены на 1/(1 − p), градиент — маска/(1 − p), seed повторяем. Ошибки — как у torch."""
import pytest
import torch
import torch.nn.functional as F

from likelib import call
from solution import dropout


def test_eval_returns_input_unchanged():
    x = torch.randn(4, 5)
    out = dropout(x, 0.5, training=False)
    assert out is x and out is F.dropout(x, 0.5, training=False), "training=False: возвращается тот же тензор, как в torch"


def test_p_zero_returns_input():
    x = torch.randn(4, 5)
    assert dropout(x, 0.0) is x, "p = 0: ничего не обнуляется, тот же тензор"


def test_p_one_zeros_everything():
    x = torch.randn(4, 5, requires_grad=True)
    out = dropout(x, 1.0)
    out.sum().backward()
    assert torch.equal(out, torch.zeros(4, 5)) and torch.equal(x.grad, torch.zeros(4, 5)), "p = 1: всё обнулено, градиент 0"


def test_default_is_training():
    torch.manual_seed(0)
    x = torch.ones(1000)
    assert (dropout(x) == 0).any(), "по умолчанию training=True (как F.dropout, в отличие от nn.Dropout в eval)"


@pytest.mark.parametrize("p", [0.1, 0.3, 0.5, 0.9])
def test_fraction_of_zeros_close_to_p(p):
    torch.manual_seed(1)
    out = dropout(torch.ones(200_000), p)
    share = (out == 0).double().mean().item()
    assert abs(share - p) < 0.01, f"доля нулей {share:.3f}, а должна быть ≈ {p}"


@pytest.mark.parametrize("p", [0.2, 0.5, 0.75])
def test_survivors_scaled(p):
    torch.manual_seed(2)
    x = torch.rand(1000) + 0.5
    out = dropout(x, p)
    kept = out != 0
    assert torch.allclose(out[kept], x[kept] / (1 - p)), f"выжившие умножены на 1 / (1 − p) = {1 / (1 - p):.3f}"


@pytest.mark.parametrize("p", [0.2, 0.5])
def test_mean_is_preserved(p):
    torch.manual_seed(3)
    x = torch.rand(200_000) + 1
    assert abs(dropout(x, p).mean().item() - x.mean().item()) < 0.02, "среднее после dropout ≈ среднему до (за счёт масштаба)"


def test_gradient_is_mask_over_keep_prob():
    torch.manual_seed(4)
    x = torch.randn(50, requires_grad=True)
    out = dropout(x, 0.4)
    out.sum().backward()
    want = (out != 0).float() / 0.6
    assert torch.allclose(x.grad, want), "градиент: 1/(1 − p) у выживших, 0 у обнулённых"


def test_seed_repeatable():
    x = torch.randn(100)
    torch.manual_seed(5)
    a = dropout(x, 0.5)
    torch.manual_seed(5)
    b = dropout(x, 0.5)
    torch.manual_seed(6)
    c = dropout(x, 0.5)
    assert torch.equal(a, b) and not torch.equal(a, c), "один seed — одна маска, другой — другая"


def test_masks_differ_between_calls():
    torch.manual_seed(7)
    x = torch.ones(100)
    assert not torch.equal(dropout(x, 0.5), dropout(x, 0.5)), "каждый вызов — новая маска"


def test_inplace_changes_input():
    torch.manual_seed(8)
    x = torch.ones(1000)
    out = dropout(x, 0.5, inplace=True)
    assert out is x and (x == 0).any() and set(x.unique().tolist()) <= {0.0, 2.0}, "inplace=True: меняется сам вход"


def test_not_inplace_keeps_input():
    torch.manual_seed(9)
    x = torch.ones(100)
    dropout(x, 0.5)
    assert torch.equal(x, torch.ones(100)), "inplace=False: вход не меняется"


@pytest.mark.parametrize("dtype", [torch.float16, torch.float32, torch.float64])
@pytest.mark.parametrize("shape", [(0,), (5,), (2, 3, 4, 4)])
def test_shape_and_dtype_kept(dtype, shape):
    out = dropout(torch.randn(shape).to(dtype), 0.3)
    assert out.shape == shape and out.dtype == dtype, "форма и dtype сохраняются"


@pytest.mark.parametrize("p", [-0.1, 1.5])
def test_bad_p_is_error_like_torch(p):
    x = torch.randn(3)
    assert call(dropout, x, p)[0] == call(F.dropout, x, p)[0] == "ValueError", f"p = {p} — ValueError, как в torch"
