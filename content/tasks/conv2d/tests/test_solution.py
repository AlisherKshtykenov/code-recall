"""conv2d против torch.nn.functional.conv2d: выход и градиенты по input, weight, bias при любых настройках."""
import pytest
import torch
import torch.nn.functional as F

from likelib import assert_grads_like, assert_like
from solution import conv2d

torch.manual_seed(0)


def t(*shape, grad=True):
    return torch.randn(*shape, dtype=torch.float64, requires_grad=grad)


@pytest.mark.parametrize("kernel", [1, 3, (3, 2), 5])
@pytest.mark.parametrize("stride", [1, 2, (2, 1)])
@pytest.mark.parametrize("padding", [0, 1, (1, 2)])
def test_kernel_stride_padding(kernel, stride, padding):
    kh, kw = (kernel, kernel) if isinstance(kernel, int) else kernel
    assert_grads_like(conv2d, F.conv2d, t(2, 3, 9, 8), t(4, 3, kh, kw), t(4), stride=stride, padding=padding)


@pytest.mark.parametrize("dilation", [1, 2, (2, 1)])
@pytest.mark.parametrize("padding", [0, 2, "valid", "same"])
def test_dilation_and_string_padding(dilation, padding):
    assert_grads_like(conv2d, F.conv2d, t(2, 2, 10, 9), t(3, 2, 3, 3), t(3), padding=padding, dilation=dilation)


@pytest.mark.parametrize("kernel", [(2, 2), (4, 3), (2, 5)])
def test_same_padding_even_kernel(kernel):
    assert_grads_like(conv2d, F.conv2d, t(1, 2, 7, 7), t(2, 2, *kernel), padding="same")  # лишний ряд — справа/снизу


@pytest.mark.parametrize("groups, c_in, c_out", [(1, 4, 6), (2, 4, 6), (4, 4, 4), (4, 4, 8)])
def test_groups_and_depthwise(groups, c_in, c_out):
    assert_grads_like(conv2d, F.conv2d, t(2, c_in, 6, 6), t(c_out, c_in // groups, 3, 3), t(c_out), padding=1, groups=groups)


@pytest.mark.parametrize("with_bias", [True, False])
def test_unbatched_input(with_bias):
    assert_grads_like(conv2d, F.conv2d, t(3, 7, 7), t(5, 3, 3, 3), t(5) if with_bias else None, padding=1)


def test_single_pixel_and_one_by_one_kernel():
    assert_grads_like(conv2d, F.conv2d, t(4, 3, 1, 1), t(2, 3, 1, 1), t(2))


def test_empty_batch():
    assert_grads_like(conv2d, F.conv2d, t(0, 3, 5, 5), t(2, 3, 3, 3), t(2))


def test_typical_defect_cnn_layer():
    x = torch.randn(8, 1, 64, 64)
    conv = torch.nn.Conv2d(1, 16, 3, padding=1)
    assert torch.allclose(conv2d(x, conv.weight, conv.bias, padding=1), conv(x), atol=1e-5), "те же веса — тот же выход, что у nn.Conv2d"


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_dtype(dtype):
    x, w = torch.randn(1, 2, 6, 6, dtype=dtype), torch.randn(3, 2, 3, 3, dtype=dtype)
    out = conv2d(x, w)
    assert out.dtype == dtype and torch.allclose(out, F.conv2d(x, w), atol=1e-5), f"dtype {dtype}"


@pytest.mark.parametrize("x, w, kw", [
    (torch.randn(1, 2, 4, 4), torch.randn(1, 1, 2, 2), {}),                       # каналы не совпадают
    (torch.randn(1, 1, 1, 1), torch.randn(1, 1, 2, 2), {}),                       # ядро больше картинки
    (torch.randn(1, 1, 4, 4), torch.randn(1, 1, 2, 2), {"padding": "same", "stride": 2}),  # same + stride
    (torch.randn(1, 1, 4, 4), torch.randn(1, 1, 2, 2), {"padding": "full"}),      # нет такого padding
    (torch.randn(4, 4), torch.randn(1, 1, 2, 2), {}),                             # нет оси каналов
    (torch.randn(1, 4, 4, 4), torch.randn(3, 2, 2, 2), {"groups": 2}),            # выходы не делятся на группы
])
def test_errors_like_torch(x, w, kw):
    assert_like(conv2d, F.conv2d, x, w, check_warning=False, **kw)
